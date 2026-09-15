import io

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

import ai_client
import config
import db
from utils import split_message


async def guard(update: Update) -> bool:
    """Returns True if the user may proceed, otherwise replies with a ban notice."""
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name)
    if db.is_banned(user.id):
        await update.message.reply_text("⛔️ دسترسی شما به این ربات مسدود شده است.")
        return False
    return True


async def _respond(update, context, user_id, user_text):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    system_prompt = db.get_setting("system_prompt", config.DEFAULT_SYSTEM_PROMPT)
    history = db.get_history(user_id)
    messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": user_text}
    ]
    model = db.get_user_model(user_id)

    try:
        reply = ai_client.chat_completion(messages, model=model)
    except ai_client.AnyModelError as e:
        await update.message.reply_text(f"❌ خطا در ارتباط با هوش مصنوعی:\n{e}")
        return

    db.add_message(user_id, "user", user_text)
    db.add_message(user_id, "assistant", reply)
    db.bump_counter(user_id, "message_count")

    for chunk in split_message(reply):
        await update.message.reply_text(chunk)

    if db.tts_enabled(user_id):
        await _send_voice_reply(update, context, reply)


async def _send_voice_reply(update, context, text):
    try:
        audio_bytes = ai_client.text_to_speech(text[:1000])
        bio = io.BytesIO(audio_bytes)
        bio.name = "reply.mp3"
        await context.bot.send_voice(chat_id=update.effective_chat.id, voice=bio)
    except ai_client.AnyModelError:
        pass  # silently skip voice if TTS not available for this account
