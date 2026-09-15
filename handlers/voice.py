import os
import tempfile

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

import ai_client
from handlers.chat import guard, _respond


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    voice = update.message.voice or update.message.audio
    tg_file = await context.bot.get_file(voice.file_id)

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "voice.ogg")
        await tg_file.download_to_drive(path)
        try:
            text = ai_client.transcribe_audio(path)
        except ai_client.AnyModelError as e:
            await update.message.reply_text(f"❌ خطا در تبدیل صدا به متن:\n{e}")
            return

    if not text.strip():
        await update.message.reply_text("متوجه نشدم چی گفتی 🙁 دوباره امتحان کن.")
        return

    await update.message.reply_text(f"📝 متن پیام شما:\n«{text}»")
    await _respond(update, context, update.effective_user.id, text)
