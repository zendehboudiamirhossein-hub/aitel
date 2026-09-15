from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
import db
from handlers import chat, image, files, zip_tools
from handlers.chat import guard
from handlers.keyboards import (
    build_main_menu, cancel_kb, file_type_kb, admin_menu_kb,
    BTN_IMAGE, BTN_FILE, BTN_ZIP, BTN_MODEL, BTN_TTS_ON, BTN_TTS_OFF,
    BTN_STATS, BTN_RESET, BTN_HELP, BTN_ADMIN, CANCEL_BTN, ALL_MENU_LABELS,
)

HELP_TEXT = (
    "سلام! 👋 من یک ربات هوش مصنوعی همه‌کاره هستم.\n\n"
    "هر پیامی بنویسی به‌عنوان چت با هوش مصنوعی جواب می‌گیره 💬\n"
    "برای بقیه‌ی کارها از دکمه‌های پایین صفحه استفاده کن:\n\n"
    "🖼 ساخت عکس — ساخت تصویر با هوش مصنوعی\n"
    "📄 ساخت فایل — PDF / Word / Excel / PowerPoint / TXT\n"
    "🗜 ساخت Zip — آرشیو گرفتن از چند فایل، یا فرستادن یک zip برای ویرایش\n"
    "🤖 انتخاب مدل — تعویض مدل هوش مصنوعی\n"
    "🔊 پاسخ صوتی — روشن/خاموش کردن پاسخ به‌صورت صدا\n"
    "📈 آمار من — آمار استفاده شخصی\n"
    "♻️ پاک‌کردن حافظه — پاک کردن تاریخچه گفتگو\n"
    "🎙 هر پیام صوتی هم به‌طور خودکار متن و پاسخ داده می‌شه.\n\n"
    "برای ساخت PDF/Word با متن دقیق خودت (بدون کمک هوش مصنوعی)، وقتی موضوع رو ازت خواستم بنویس:\n"
    "raw: متن دقیق من اینجاست"
)


# ------------------------------------------------------------------ entry point

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name)
    await update.message.reply_text(HELP_TEXT, reply_markup=build_main_menu(user.id))


# ------------------------------------------------------------------ central text dispatcher

async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return

    text = (update.message.text or "").strip()
    user_id = update.effective_user.id

    if text == CANCEL_BTN:
        context.user_data.pop("awaiting", None)
        context.user_data.pop("zip_collecting", None)
        await update.message.reply_text("باشه، لغو شد.", reply_markup=build_main_menu(user_id))
        return

    if text in ALL_MENU_LABELS:
        context.user_data.pop("awaiting", None)
        await _dispatch_menu_button(update, context, text)
        return

    awaiting = context.user_data.get("awaiting")
    if awaiting:
        context.user_data.pop("awaiting", None)
        await _handle_awaiting(update, context, awaiting, text)
        return

    # default: plain conversation with the AI
    await chat._respond(update, context, user_id, text)


async def _dispatch_menu_button(update, context, text):
    user_id = update.effective_user.id

    if text == BTN_IMAGE:
        context.user_data["awaiting"] = "image"
        await update.message.reply_text("🖼 توضیح تصویری که می‌خوای بسازم رو بنویس:", reply_markup=cancel_kb())

    elif text == BTN_FILE:
        await update.message.reply_text("📄 نوع فایل رو انتخاب کن:", reply_markup=file_type_kb())

    elif text == BTN_ZIP:
        await zip_tools.zip_start(update, context)

    elif text == BTN_MODEL:
        await _show_model_menu(update, context)

    elif text in (BTN_TTS_ON, BTN_TTS_OFF):
        enabled = db.toggle_tts(user_id)
        await update.message.reply_text(
            "🔊 از الان پاسخ صوتی هم برات می‌فرستم." if enabled else "🔇 پاسخ صوتی خاموش شد.",
            reply_markup=build_main_menu(user_id),
        )

    elif text == BTN_STATS:
        user = db.get_or_create_user(user_id)
        stats_text = (
            "📈 آمار شما:\n"
            f"پیام‌های چت: {user['message_count']}\n"
            f"تصاویر ساخته‌شده: {user['image_count']}\n"
            f"فایل‌های ساخته‌شده: {user['file_count']}\n"
            f"مدل فعلی: {db.get_user_model(user_id)}\n"
            f"عضو از: {user['created_at'][:10]}"
        )
        await update.message.reply_text(stats_text)

    elif text == BTN_RESET:
        db.clear_history(user_id)
        await update.message.reply_text("✅ حافظه مکالمه پاک شد.")

    elif text == BTN_HELP:
        await update.message.reply_text(HELP_TEXT, reply_markup=build_main_menu(user_id))

    elif text == BTN_ADMIN:
        if not db.is_admin(user_id):
            await update.message.reply_text("⛔️ این بخش فقط برای ادمین‌هاست.")
            return
        await update.message.reply_text(_admin_stats_text(), reply_markup=admin_menu_kb())


async def _handle_awaiting(update, context, awaiting, text):
    user_id = update.effective_user.id

    if awaiting == "image":
        await image.generate_image_for(update, context, text)

    elif awaiting.startswith("file:"):
        kind = awaiting.split(":", 1)[1]
        await files.generate_file(update, context, kind, text)

    elif awaiting == "admin_broadcast":
        if not db.is_admin(user_id):
            return
        db.queue_broadcast(text)
        await update.message.reply_text(
            "✅ پیام در صف قرار گرفت و طی چند ثانیه برای همه کاربران ارسال می‌شود.",
            reply_markup=build_main_menu(user_id),
        )

    elif awaiting == "admin_setmodel":
        if not db.is_admin(user_id):
            return
        db.set_setting("default_model", text.strip())
        await update.message.reply_text(
            f"✅ مدل پیش‌فرض روی «{text.strip()}» تنظیم شد.", reply_markup=build_main_menu(user_id)
        )

    elif awaiting == "admin_setprompt":
        if not db.is_admin(user_id):
            return
        db.set_setting("system_prompt", text)
        await update.message.reply_text(
            "✅ System prompt پیش‌فرض به‌روزرسانی شد.", reply_markup=build_main_menu(user_id)
        )

    else:
        await chat._respond(update, context, user_id, text)


# ------------------------------------------------------------------ model picker

async def _show_model_menu(update, context):
    user_id = update.effective_user.id
    current = db.get_user_model(user_id)
    buttons = [
        [InlineKeyboardButton(("✅ " if m == current else "") + m, callback_data=f"setmodel:{m}")]
        for m in config.AVAILABLE_CHAT_MODELS
    ]
    await update.message.reply_text(
        f"مدل فعلی شما: {current}\nیک مدل جدید انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    model = query.data.split(":", 1)[1]
    db.set_user_model(update.effective_user.id, model)
    await query.edit_message_text(f"✅ مدل شما روی «{model}» تنظیم شد.")


# ------------------------------------------------------------------ file-type picker

async def filetype_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kind = query.data.split(":", 1)[1]
    context.user_data["awaiting"] = f"file:{kind}"
    await query.edit_message_text(f"نوع انتخابی: {kind}")
    await query.message.reply_text(
        "موضوع یا متن فایل رو بنویس.\n"
        "(برای متن دقیق خودت بدون کمک هوش مصنوعی: raw: متن شما — فقط برای PDF و Word)",
        reply_markup=cancel_kb(),
    )


# ------------------------------------------------------------------ admin panel (button driven)

def _admin_stats_text():
    stats = db.get_stats()
    return (
        "🛠 پنل مدیریت\n\n"
        f"👥 کاربران: {stats['total_users']} (مسدود: {stats['banned']})\n"
        f"🟢 فعال امروز: {stats['active_today']}\n"
        f"💬 کل پیام‌ها: {stats['total_messages']}\n"
        f"🖼 کل تصاویر: {stats['total_images']}\n"
        f"📄 کل فایل‌ها: {stats['total_files']}"
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not db.is_admin(user_id):
        await query.edit_message_text("⛔️ دسترسی نداری.")
        return

    parts = query.data.split(":")
    action = parts[1]

    if action == "broadcast":
        context.user_data["awaiting"] = "admin_broadcast"
        await query.message.reply_text("📢 متن پیام همگانی رو بنویس:", reply_markup=cancel_kb())

    elif action == "setmodel":
        context.user_data["awaiting"] = "admin_setmodel"
        hint = "، ".join(config.AVAILABLE_CHAT_MODELS)
        await query.message.reply_text(
            f"🤖 نام مدل جدید پیش‌فرض رو بنویس.\nنمونه‌ها: {hint}", reply_markup=cancel_kb()
        )

    elif action == "setprompt":
        context.user_data["awaiting"] = "admin_setprompt"
        await query.message.reply_text("📝 متن System Prompt جدید رو بنویس:", reply_markup=cancel_kb())

    elif action == "refresh":
        await query.edit_message_text(_admin_stats_text(), reply_markup=admin_menu_kb())

    elif action == "users":
        page = int(parts[2]) if len(parts) > 2 else 0
        await _render_admin_users(query, page)


def _admin_users_kb(users, page, has_more):
    buttons = []
    for u in users:
        label = f"{u['telegram_id']} @{u['username'] or '-'}"
        ban_label = "✅ رفع مسدودی" if u["is_banned"] else "🚫 مسدود کن"
        admin_label = "👤 حذف ادمین" if u["is_admin"] else "👑 ادمین کن"
        buttons.append([InlineKeyboardButton(label, callback_data="noop")])
        buttons.append([
            InlineKeyboardButton(ban_label, callback_data=f"adminuser:{u['telegram_id']}:{'unban' if u['is_banned'] else 'ban'}"),
            InlineKeyboardButton(admin_label, callback_data=f"adminuser:{u['telegram_id']}:{'demote' if u['is_admin'] else 'promote'}"),
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin:users:{page-1}"))
    if has_more:
        nav.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"admin:users:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin:refresh")])
    return InlineKeyboardMarkup(buttons)


async def _render_admin_users(query, page):
    page_size = 5
    users = db.list_users(limit=page_size + 1, offset=page * page_size)
    has_more = len(users) > page_size
    users = users[:page_size]
    if not users:
        await query.edit_message_text("کاربری یافت نشد.", reply_markup=admin_menu_kb())
        return
    await query.edit_message_text(
        f"👥 مدیریت کاربران (صفحه {page + 1})", reply_markup=_admin_users_kb(users, page, has_more)
    )


async def adminuser_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await query.answer("⛔️ دسترسی نداری.", show_alert=True)
        return
    await query.answer()
    _, uid, action = query.data.split(":")
    uid = int(uid)
    if action == "ban":
        db.set_ban(uid, True)
    elif action == "unban":
        db.set_ban(uid, False)
    elif action == "promote":
        db.set_admin(uid, True)
    elif action == "demote":
        db.set_admin(uid, False)
    await _render_admin_users(query, 0)


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
