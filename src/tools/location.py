from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from .schema import create_function_response
import asyncio
import logging

logger = logging.getLogger(__name__)

# State definitions
LOCATION = 1

# Store pending location requests
pending_location_requests = {}

async def get_user_location(reason: str = None) -> dict:
    """Request the user's location and wait for response."""
    try:
        chat_id = pending_location_requests.get("chat_id")
        update = pending_location_requests.get("update")
        
        if not chat_id or not update:
            return create_function_response(
                error="Location request failed: Missing chat context"
            )

        # Check if we already have a location for this request
        if "location" in pending_location_requests:
            location = pending_location_requests["location"]
            logger.info(f"Using cached location for chat_id {chat_id}: {location.latitude}, {location.longitude}")
            return create_function_response({
                "latitude": location.latitude,
                "longitude": location.longitude
            })

        # Create location request button
        keyboard = [[KeyboardButton("Share Location 📍", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        # Send request message
        message = "Please share your location"
        if reason:
            message += f" ({reason})"
        await update.message.reply_text(message, reply_markup=reply_markup)

        # Create and store future before waiting
        location_future = asyncio.get_event_loop().create_future()
        pending_location_requests[chat_id] = location_future
        
        logger.info(f"Waiting for location from chat_id: {chat_id}")
        location = await asyncio.wait_for(location_future, timeout=30.0)
        
        if location:
            logger.info(f"Received location for chat_id {chat_id}: {location.latitude}, {location.longitude}")
            # Cache the location for subsequent requests
            pending_location_requests["location"] = location
            return create_function_response({
                "latitude": location.latitude,
                "longitude": location.longitude
            })
        else:
            return create_function_response(
                error="Location data was invalid"
            )

    except asyncio.TimeoutError:
        logger.warning(f"Location request timed out for chat_id: {chat_id}")
        return create_function_response(
            error="Location request timed out. Please try again."
        )
    except Exception as e:
        logger.error(f"Error in get_user_location: {str(e)}", exc_info=True)
        return create_function_response(
            error=f"Location request failed: {str(e)}"
        )
    finally:
        # Cleanup only the future, keep the location cached
        if chat_id in pending_location_requests:
            del pending_location_requests[chat_id]
        try:
            # Remove keyboard
            if update and update.message:
                await update.message.reply_text(
                    "Thanks!", 
                    reply_markup=ReplyKeyboardRemove()
                )
        except Exception as e:
            logger.error(f"Error cleaning up location request: {str(e)}")

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle received location."""
    try:
        chat_id = update.effective_chat.id
        logger.info(f"Received location update for chat_id: {chat_id}")
        
        # Store the location for immediate and future use
        pending_location_requests["location"] = update.message.location
        
        if chat_id in pending_location_requests:
            future = pending_location_requests.get(chat_id)
            if isinstance(future, asyncio.Future) and not future.done():
                logger.info(f"Setting location result for chat_id: {chat_id}")
                future.set_result(update.message.location)
            else:
                logger.warning(f"Found invalid future for chat_id: {chat_id}")
        else:
            logger.warning(f"No pending location request for chat_id: {chat_id}")
            
    except Exception as e:
        logger.error(f"Error in handle_location: {str(e)}", exc_info=True)