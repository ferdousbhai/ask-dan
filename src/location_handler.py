import asyncio
import logging
from pydantic import BaseModel, Field, PrivateAttr
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from .tools.schema import create_function_response

logger = logging.getLogger(__name__)

# Replace the simple dict with a structured class


class LocationRequest(BaseModel):
    requests: dict[int, dict] = Field(default_factory=dict)
    _lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    class Config:
        arbitrary_types_allowed = True

    async def add_request(self, chat_id: int, update: Update) -> asyncio.Future:
        async with self._lock:
            future = asyncio.Future()
            self.requests[chat_id] = {
                'future': future,
                'update': update,
                'timestamp': asyncio.get_event_loop().time()
            }
            return future

    async def get_request(self, chat_id: int) -> dict:
        async with self._lock:
            return self.requests.get(chat_id)

    async def remove_request(self, chat_id: int) -> None:
        async with self._lock:
            self.requests.pop(chat_id, None)

# Replace the global dict with an instance
location_requests = LocationRequest()

async def get_user_location(update: Update, context: ContextTypes.DEFAULT_TYPE, reason: str = None) -> dict:
    """Request user location with an optional reason."""
    chat_id = update.effective_chat.id
    
    if not chat_id or not update:
        return create_function_response(
            error="Location request failed: Missing chat context"
        )

    future = await location_requests.add_request(chat_id, update)

    # Build location keyboard
    keyboard = [[KeyboardButton("Share Location 📍", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    # Send request
    message = "Please share your location"
    if reason:
        message += f" ({reason})"
    
    await update.message.reply_text(message, reply_markup=reply_markup)

    try:
        # Wait for location with timeout
        location = await asyncio.wait_for(future, timeout=300.0)  # 5 minute timeout
        return create_function_response(
            result={
                "latitude": location.latitude,
                "longitude": location.longitude
            }
        )
    except asyncio.TimeoutError:
        return create_function_response(
            error="Location request timed out. Please try again."
        )
    finally:
        # Cleanup
        if chat_id in location_requests.requests:
            del location_requests.requests[chat_id]

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming location messages."""
    chat_id = update.effective_chat.id
    logger.info(f"Received location update for chat_id: {chat_id}")

    request = await location_requests.get_request(chat_id)
    if request and not request['future'].done():
        location = update.message.location
        if location:
            logger.info(f"Setting location result: {location.latitude}, {location.longitude}")
            request['future'].set_result(location)
            await location_requests.remove_request(chat_id)
            
            await update.message.reply_text(
                "Thanks for sharing your location!",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            request['future'].set_exception(ValueError("No location data received"))
            await location_requests.remove_request(chat_id)
    else:
        logger.warning(f"Received unsolicited location from chat_id: {chat_id}")
        await update.message.reply_text(
            "I haven't requested your location. I'll only ask for it when needed for specific features."
        ) 

async def cleanup_stale_requests():
    """Periodically clean up stale location requests."""
    while True:
        try:
            current_time = asyncio.get_event_loop().time()
            async with location_requests._lock:
                for chat_id, request in list(location_requests.requests.items()):
                    # Remove requests older than 5 minutes
                    if current_time - request['timestamp'] > 300:
                        if not request['future'].done():
                            request['future'].set_exception(
                                asyncio.TimeoutError("Location request expired")
                            )
                        await location_requests.remove_request(chat_id)
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
        await asyncio.sleep(60)  # Run cleanup every minute

# Start cleanup task in your main.py or where you initialize the bot
asyncio.create_task(cleanup_stale_requests()) 