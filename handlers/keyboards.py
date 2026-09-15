from telegram import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

import db

BTN_IMAGE = "🖼 ساخت عکس"
BTN_FILE = "📄 ساخت فایل"
BTN_ZIP = "🗜 ساخت Zip"
BTN_MODEL = "🤖 انتخاب مدل"
BTN_TTS_ON = "🔇 خاموش‌کردن پاسخ صوتی"
BTN_TTS_OFF = "🔊 روشن‌کردن پاسخ صوتی"
BTN_STATS = "📈 آمار من"
BTN_RESET = "♻️ پاک‌کردن حافظه"
BTN_HELP = "ℹ️ راهنما"
BTN_ADMIN = "🛠 پنل مدیریت"
CANCEL_BTN = "❌ انصراف"

# every label the main menu can ever show (used to detect "user pressed a button"
# vs. "user is answering a pending question")
ALL_MENU_LABELS = {
    BTN_IMAGE, BTN_FILE, BTN_ZIP, BTN_MODEL, BTN_TTS_ON, BTN_TTS_OFF,
    BTN_STATS, BTN_RESET, BTN_HELP, BTN_ADMIN, CANCEL_BTN,
}


def build_main_menu(user_id) -> ReplyKeyboardMarkup:
    tts_label = BTN_TTS_ON if db.tts_enabled(user_id) else BTN_TTS_OFF
    rows = [
        [KeyboardButton(BTN_IMAGE), KeyboardButton(BTN_FILE)],
        [KeyboardButton(BTN_ZIP), KeyboardButton(BTN_MODEL)],
        [KeyboardButton(tts_label), KeyboardButton(BTN_STATS)],
        [KeyboardButton(BTN_RESET), KeyboardButton(BTN_HELP)],
    ]
    if db.is_admin(user_id):
        rows.append([KeyboardButton(BTN_ADMIN)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(CANCEL_BTN)]], resize_keyboard=True)


def file_type_kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📄 PDF", callback_data="filetype:pdf"),
         InlineKeyboardButton("📝 Word", callback_data="filetype:docx")],
        [InlineKeyboardButton("📊 Excel", callback_data="filetype:xlsx"),
         InlineKeyboardButton("📽 PowerPoint", callback_data="filetype:pptx")],
        [InlineKeyboardButton("🧾 متن ساده (txt)", callback_data="filetype:txt")],
    ]
    return InlineKeyboardMarkup(buttons)


def zip_action_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ پایان و دریافت آرشیو", callback_data="zipsession:done"),
        InlineKeyboardButton("❌ لغو", callback_data="zipsession:cancel"),
    ]])


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="admin:broadcast")],
        [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin:users:0")],
        [InlineKeyboardButton("🤖 تنظیم مدل پیش‌فرض", callback_data="admin:setmodel")],
        [InlineKeyboardButton("📝 تنظیم System Prompt", callback_data="admin:setprompt")],
        [InlineKeyboardButton("🔄 به‌روزرسانی آمار", callback_data="admin:refresh")],
    ])
