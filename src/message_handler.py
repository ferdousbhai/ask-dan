from pydantic import BaseModel
import telegram

class MessageContent(BaseModel):
    type: str
    content_id: str | None = None  # For media file_ids
    text: str | None = None        # For text or captions
    
class Message(BaseModel):
    content: MessageContent
    metadata: dict

def create_message_from_telegram(tg_message: telegram.Message) -> Message | None:
    """Creates a Message object from a Telegram Message object."""
    
    # Mapping of message attributes to their corresponding types
    MESSAGE_TYPES = {
        'text': ('text', lambda m: m.text),
        'photo': ('photo', lambda m: m.photo[-1].file_id),
        'video': ('video', lambda m: m.video.file_id),
        'audio': ('audio', lambda m: m.audio.file_id),
        'document': ('document', lambda m: m.document.file_id),
        'sticker': ('sticker', lambda m: m.sticker.file_id),
        'voice': ('voice', lambda m: m.voice.file_id),
    }

    # Find the first matching message type
    for attr, (type_name, content_getter) in MESSAGE_TYPES.items():
        if getattr(tg_message, attr):
            return Message(
                content=MessageContent(
                    type=type_name,
                    content_id=content_getter(tg_message) if attr != 'text' else None,
                    text=content_getter(tg_message) if attr == 'text' else tg_message.caption
                ),
                metadata={
                    "from": tg_message.from_user.to_dict() if tg_message.from_user else None,
                    "chat": tg_message.chat.to_dict() if tg_message.chat else None,
                    "reply_to": tg_message.reply_to_message.to_dict() if tg_message.reply_to_message else None,
                }
            )
    
    return None