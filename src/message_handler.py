import asyncio
import logging
import os
import re
from google import genai
from google.genai import types
from google.genai.chats import AsyncChat
from telegram import Update, Message as TelegramMessage
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify
from src.safety import safety_settings
from src.tools.schema import tools
from src.tools.url import scrape_url
from src.tools.research import get_online_research
from src.system_prompt import get_system_prompt
from src.utils import show_typing_indicator, split_response_into_paragraphs
from typing import Final

logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# In-memory chat history storage
chat_by_id: dict[int, AsyncChat] = {}

# Constants for file size limits (in bytes)
MAX_PHOTO_SIZE: Final = 20 * 1024 * 1024  # 20MB
MAX_VIDEO_SIZE: Final = 50 * 1024 * 1024  # 50MB
MAX_AUDIO_SIZE: Final = 20 * 1024 * 1024  # 20MB
MAX_DOC_SIZE: Final = 30 * 1024 * 1024   # 30MB
MAX_TEXT_TOKENS: Final = 100000  # Maximum tokens for text content

def create_chat(chat_id: int, system_instruction: str | None = None, temperature: float = 1) -> AsyncChat:
    chat: AsyncChat = client.aio.chats.create(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            safety_settings=safety_settings,
            tools=tools
        )
    )
    chat_by_id[chat_id] = chat
    return chat

async def create_message_contents(message: TelegramMessage) -> list:
    """Prepare message contents for the model, handling images, video, audio, documents and text.

    Args:
        message: Telegram message object containing media and/or text

    Returns:
        list: List of contents (media blobs and/or text) ready for the model

    Raises:
        ValueError: If file size exceeds limits or file type is unsupported
    """
    contents = []

    # Handle photo
    if message.photo:
        photo = message.photo[-1]
        if photo.file_size > MAX_PHOTO_SIZE:
            raise ValueError(f"Image file too large. Maximum size is {MAX_PHOTO_SIZE // (1024*1024)}MB")

        try:
            photo_file = await photo.get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            contents.append(types.Part(
                inline_data=types.Blob(
                    mime_type="image/jpeg",
                    data=photo_bytes
                )
            ))
        except Exception as e:
            raise ValueError(f"Failed to process image: {str(e)}")

    # Handle video
    elif message.video:
        if message.video.file_size > MAX_VIDEO_SIZE:
            raise ValueError(f"Video file too large. Maximum size is {MAX_VIDEO_SIZE // (1024*1024)}MB")

        try:
            video_file = await message.video.get_file()
            video_bytes = await video_file.download_as_bytearray()
            contents.append(types.Part(
                inline_data=types.Blob(
                    mime_type="video/mp4",
                    data=video_bytes
                )
            ))
        except Exception as e:
            raise ValueError(f"Failed to process video: {str(e)}")

    # Handle audio/voice messages
    elif message.voice or message.audio:
        audio_msg = message.voice or message.audio
        if audio_msg.file_size > MAX_AUDIO_SIZE:
            raise ValueError(f"Audio file too large. Maximum size is {MAX_AUDIO_SIZE // (1024*1024)}MB")

        try:
            audio_file = await audio_msg.get_file()
            audio_bytes = await audio_file.download_as_bytearray()
            contents.append(types.Part(
                inline_data=types.Blob(
                    mime_type="audio/ogg" if message.voice else "audio/mpeg",
                    data=audio_bytes
                )
            ))
        except Exception as e:
            raise ValueError(f"Failed to process audio: {str(e)}")

    # Handle documents/files
    elif message.document:
        if message.document.file_size > MAX_DOC_SIZE:
            raise ValueError(f"Document too large. Maximum size is {MAX_DOC_SIZE // (1024*1024)}MB")

        try:
            doc_file = await message.document.get_file()
            doc_bytes = await doc_file.download_as_bytearray()
            mime_type = message.document.mime_type or "application/octet-stream"

            # Handle PDFs
            if mime_type == "application/pdf":
                contents.append(types.Part(
                    inline_data=types.Blob(
                        mime_type=mime_type,
                        data=doc_bytes
                    )
                ))
            # Handle text files
            elif mime_type.startswith("text/"):
                try:
                    text_content = doc_bytes.decode('utf-8')
                    # Rough estimation of tokens (1 token ≈ 4 characters)
                    if len(text_content) > MAX_TEXT_TOKENS * 4:
                        raise ValueError(f"Text content too long. Maximum {MAX_TEXT_TOKENS} tokens allowed.")
                    contents.append(text_content)
                except UnicodeDecodeError:
                    raise ValueError("Unable to decode text file. Please ensure it's in UTF-8 encoding.")
            else:
                supported_types = ["PDF documents", "text files"]
                raise ValueError(
                    f"Unsupported file type: {mime_type}. "
                    f"Currently supporting: {', '.join(supported_types)}."
                )
        except Exception as e:
            raise ValueError(f"Failed to process document: {str(e)}")

    # Handle text content for any media
    text_content = message.caption or message.text
    if text_content:
        # Rough token count check for text
        if len(text_content) > MAX_TEXT_TOKENS * 4:
            raise ValueError(f"Text content too long. Maximum {MAX_TEXT_TOKENS} tokens allowed.")
        contents.append(text_content)
    elif message.photo:
        contents.append("Please analyze and describe this image.")
    elif message.video:
        contents.append("Please analyze and describe this video.")
    elif message.voice or message.audio:
        contents.append("Please transcribe and analyze this audio content.")
    elif message.document and message.document.mime_type == "application/pdf":
        contents.append("Please analyze and summarize this PDF document.")

    return contents

async def handle_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages from users."""
    message = update.message
    if not message or not (message.text or message.photo or message.video or message.voice or message.audio or message.document):
        return

    chat_id = update.effective_chat.id
    chat: AsyncChat = chat_by_id.get(chat_id) or create_chat(chat_id, get_system_prompt(message))
    typing_task = asyncio.create_task(show_typing_indicator(update.effective_chat, stop_typing_event := asyncio.Event()))

    try:
        contents = await create_message_contents(message)
        response = await chat.send_message(contents)

        # Sequentially process function calls
        while response.function_calls:
            function_call = response.function_calls[0]
            function_name = function_call.name
            function_args = function_call.args

            try:
                # Execute the appropriate function
                if function_name == "get_online_research":
                    result = await get_online_research(**function_args)
                elif function_name == "scrape_url":
                    result = await scrape_url(**function_args)
                elif function_name == "start_a_new_conversation":
                    chat = create_chat(chat_id, get_system_prompt(message))
                    result = "Conversation reset successfully"
                else:
                    raise ValueError(f"Unknown function: {function_name}")

                # Format the function response according to SDK specifications
                function_response = {
                    "name": function_name,
                    "response": {
                        "result": result if not isinstance(result, Exception) else None,
                        "error": str(result) if isinstance(result, Exception) else None
                    }
                }

                # Send function response back to model
                response = await chat.send_message(
                    types.Part.from_function_response(**function_response)
                )

            except Exception as e:
                logger.error(f"Error executing function {function_name}: {str(e)}", exc_info=True)
                # Send error response back to model
                response = await chat.send_message(
                    types.Part.from_function_response(
                        name=function_name,
                        response={"error": str(e)}
                    )
                )

        # Process final text response
        logger.info(f"Model response text: {response.text}")
        response_text = re.sub(r'<think>[\s\S]*?</think>', '', response.text)

        # Split and send paragraphs
        paragraphs = split_response_into_paragraphs(response_text)
        for paragraph in paragraphs:
            if paragraph:
                await update.message.reply_text(
                    markdownify(paragraph),
                    parse_mode="MarkdownV2"
                )

    except Exception as e:
        logger.error(f"Error in message handling: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "I apologize, but I encountered an error processing your request. "
            "Please try again later or contact @ferdousbhai for support."
        )
    finally:
        stop_typing_event.set()
        await typing_task