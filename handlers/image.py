import io

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

import ai_client
import db
from handlers.keyboards import build_main_menu


async def generate_image_for(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    prompt = (prompt or "").strip()
    user_id = update.effective_user.id
    if not prompt:
        await update.message.reply_text(
            "توضیح تصویر نمی‌تواند خالی باشد. دوباره از دکمه «🖼 ساخت عکس» استفاده کن.",
            reply_markup=build_main_menu(user_id),
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
    status = await update.message.reply_text("🎨 در حال ساخت تصویر...")

    try:
        images = await ai_client.generate_image(prompt)
    except ai_client.AnyModelError as e:
        await status.edit_text(f"❌ خطا در ساخت تصویر:\n{e}")
        await update.message.reply_text("منوی اصلی:", reply_markup=build_main_menu(user_id))
        return

    await status.delete()
    for i, img_bytes in enumerate(images):
        bio = io.BytesIO(img_bytes)
        bio.name = "image.png"
        last = i == len(images) - 1
        await update.message.reply_photo(
            photo=bio,
            caption=f"🖼 {prompt[:900]}",
            reply_markup=build_main_menu(user_id) if last else None,
        )

    db.bump_counter(user_id, "image_count")
