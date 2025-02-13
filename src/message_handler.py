import asyncio
import logging
from google.genai import types
from google.genai.chats import AsyncChat
from telegram import Update, Message as TelegramMessage, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from telegramify_markdown import telegramify
from .chat import get_chat, create_chat, clear_chat
from .functions.online_research import get_online_research
from .functions.url import scrape_url
from .system_prompt import get_system_prompt
from .utils import show_typing_indicator
from typing import Final

logger = logging.getLogger(__name__)

# Constants for file size limits (in bytes)
MAX_PHOTO_SIZE: Final = 20 * 1024 * 1024  # 20MB
MAX_VIDEO_SIZE: Final = 50 * 1024 * 1024  # 50MB
MAX_AUDIO_SIZE: Final = 20 * 1024 * 1024  # 20MB
MAX_DOC_SIZE: Final = 30 * 1024 * 1024   # 30MB
MAX_TEXT_TOKENS: Final = 100000  # Maximum tokens for text content


async def create_message_contents(message: TelegramMessage) -> list[str | types.Part]:
    """Prepare message contents for the model, handling images, video, audio, documents and text.

    Args:
        message: Telegram message object containing media and/or text

    Returns:
        list[str | types.Part]: List of contents where each item is either
            - str: For text content or location data
            - types.Part: For media content (images, video, audio, PDFs)

    Raises:
        ValueError: If file size exceeds limits or file type is unsupported
    """
    contents = []

    # Handle location messages
    if message.location:
        contents.append(f"Location: Latitude {message.location.latitude}, Longitude {message.location.longitude}")
        return contents

    try:
        # Handle photo
        if message.photo:
            photo = message.photo[-1]  # Get highest resolution photo
            contents.append(await handle_media_content(photo, MAX_PHOTO_SIZE, "image/jpeg"))

        # Handle video
        elif message.video:
            contents.append(await handle_media_content(message.video, MAX_VIDEO_SIZE, "video/mp4"))

        # Handle audio/voice messages
        elif message.voice or message.audio:
            audio_msg = message.voice or message.audio
            mime_type = "audio/ogg" if message.voice else "audio/mpeg"
            contents.append(await handle_media_content(audio_msg, MAX_AUDIO_SIZE, mime_type))

        # Handle documents/files
        elif message.document:
            if message.document.file_size > MAX_DOC_SIZE:
                raise ValueError(f"File size limit exceeded: Maximum allowed is {MAX_DOC_SIZE // (1024*1024)}MB")

            mime_type = message.document.mime_type or "application/octet-stream"

            if mime_type == "application/pdf":
                contents.append(await handle_media_content(message.document, MAX_DOC_SIZE, mime_type))
            elif mime_type.startswith("text/"):
                doc_file = await message.document.get_file()
                doc_bytes = await doc_file.download_as_bytearray()
                try:
                    text_content = doc_bytes.decode('utf-8')
                    if len(text_content) > MAX_TEXT_TOKENS * 4:
                        raise ValueError(f"Text length limit exceeded: Maximum {MAX_TEXT_TOKENS} tokens allowed")
                    contents.append(text_content)
                except UnicodeDecodeError:
                    raise ValueError("Invalid file encoding: Please ensure the text file is UTF-8 encoded")
            else:
                supported_types = ["PDF documents", "text files"]
                raise ValueError(
                    f"Unsupported file type: {mime_type}. "
                    f"Supported formats are: {', '.join(supported_types)}"
                )

        # Handle text content for any media
        text_content = message.caption or message.text
        if text_content:
            if len(text_content) > MAX_TEXT_TOKENS * 4:
                raise ValueError(f"Text length limit exceeded: Maximum {MAX_TEXT_TOKENS} tokens allowed")
            contents.append(text_content)
        elif message.photo:
            contents.append("here's an image.")
        elif message.video:
            contents.append("here's a video.")
        elif message.voice or message.audio:
            contents.append("here's an audio message.")
        elif message.document and message.document.mime_type == "application/pdf":
            contents.append("here's a PDF document.")

    except Exception as e:
        raise ValueError(f"Content processing error: {str(e)}")

    return contents


async def handle_media_content(media_obj, max_size: int, mime_type: str) -> types.Part:
    """Helper function to handle media content processing."""
    if media_obj.file_size > max_size:
        raise ValueError(f"File size limit exceeded: Maximum allowed is {max_size // (1024*1024)}MB")

    try:
        file = await media_obj.get_file()
        bytes_data = await file.download_as_bytearray()
        return types.Part(
            inline_data=types.Blob(
                mime_type=mime_type,
                data=bytes_data
            )
        )
    except Exception as e:
        raise ValueError(f"Media processing error: {str(e)}")


async def handle_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages from users."""
    message = update.message
    if not message:
        return

    chat_id = update.effective_chat.id

    chat: AsyncChat = get_chat(chat_id) or create_chat(chat_id, get_system_prompt(message))
    typing_task = asyncio.create_task(show_typing_indicator(update.effective_chat, stop_typing_event := asyncio.Event()))

    async def request_location(text_to_send: str):
        await update.message.reply_text(
            text_to_send,
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("Share Location 📍", request_location=True)]],
                one_time_keyboard=True
            )
        )
        return None

    FUNCTION_HANDLERS = {
        "start_a_new_conversation": lambda reason: clear_chat(update.effective_chat.id, reason),
        "get_online_research": get_online_research,
        "scrape_url": scrape_url,
        "request_user_location": request_location
    }

    try:
        contents = await create_message_contents(message)
        response = await chat.send_message(contents)

        # Process function calls one at a time
        while response.function_calls:
            function_call = response.function_calls[0]
            function_name = function_call.name
            function_args = function_call.args

            handler = FUNCTION_HANDLERS.get(function_name)
            logger.info(f"Function call: {function_name} with args: {function_args}")
            try:
                if not handler:
                    function_response = {"error": f"Unknown function: {function_name}"}
                else:
                    result = await handler(**function_args) if asyncio.iscoroutinefunction(handler) else handler(**function_args)
                    if result is None:
                        return  # Exit early if no response is required from the tool
                    function_response = {"output": result}
            except Exception as e:
                function_response = {"error": str(e)}

            response = await chat.send_message(
                types.Part.from_function_response(
                    name=function_name,
                    response=function_response
                )
            )

        # Only try to send text response if there's actual text content
        if response.text:
            chunks = await telegramify(response.text)
            for chunk in chunks:
                await update.message.reply_text(
                    chunk.content,
                    parse_mode="MarkdownV2",
                )

    except Exception as e:
        logger.error(f"Error in message handling: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"Sorry, I encountered an error: {str(e)}",
            parse_mode=None
        )
    finally:
        stop_typing_event.set()
        await typing_task