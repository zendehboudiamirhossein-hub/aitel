import logging
import threading

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

import config
import db
from handlers import menu, zip_tools
from utils import ensure_persian_font

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception", exc_info=context.error)
    db.log_event("error", f"{context.error}")
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("❌ یک خطای غیرمنتظره پیش اومد. دوباره امتحان کن.")
        except Exception:
            pass


async def process_broadcast_queue(context: ContextTypes.DEFAULT_TYPE):
    """Runs periodically (JobQueue) so the Flask admin panel, which lives in another thread,
    can ask the bot to broadcast a message without touching the asyncio event loop directly."""
    pending = db.get_pending_broadcasts()
    for item in pending:
        user_ids = db.all_user_ids()
        sent = 0
        for uid in user_ids:
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 {item['message']}")
                sent += 1
            except Exception:
                continue
        db.mark_broadcast_sent(item["id"], sent)
        db.log_event("info", f"Broadcast #{item['id']} sent to {sent}/{len(user_ids)} users")


def voice_handler_lazy():
    # imported lazily to avoid a circular import at module load time
    from handlers.voice import handle_voice
    return handle_voice


def build_application() -> Application:
    # concurrent_updates=True lets python-telegram-bot process multiple users'
    # messages at the same time instead of queuing them one-by-one. Combined
    # with the now-async ai_client calls, one user's slow AI request no longer
    # blocks everyone else.
    application = Application.builder().token(config.BOT_TOKEN).concurrent_updates(True).build()

    # /start is the only slash command left - Telegram always needs an entry point.
    # Every other feature is reachable only through the reply/inline keyboards.
    application.add_handler(CommandHandler("start", menu.start))

    # inline keyboard callbacks
    application.add_handler(CallbackQueryHandler(menu.model_callback, pattern=r"^setmodel:"))
    application.add_handler(CallbackQueryHandler(menu.filetype_callback, pattern=r"^filetype:"))
    application.add_handler(CallbackQueryHandler(menu.admin_callback, pattern=r"^admin:"))
    application.add_handler(CallbackQueryHandler(menu.adminuser_callback, pattern=r"^adminuser:"))
    application.add_handler(CallbackQueryHandler(menu.noop_callback, pattern=r"^noop$"))
    application.add_handler(CallbackQueryHandler(zip_tools.zipsession_callback, pattern=r"^zipsession:"))
    application.add_handler(CallbackQueryHandler(zip_tools.zip_menu_callback, pattern=r"^zip:"))

    # media
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_handler_lazy()))
    application.add_handler(MessageHandler(filters.Document.ALL, zip_tools.handle_document_router))
    application.add_handler(MessageHandler(filters.PHOTO, zip_tools.handle_photo_router))

    # every remaining text message (menu button taps + free chat) goes through one dispatcher
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu.handle_menu_text))

    application.add_error_handler(error_handler)

    if application.job_queue is not None:
        application.job_queue.run_repeating(process_broadcast_queue, interval=5, first=5)

    return application


def run_admin_panel():
    from admin_panel.app import create_app
    app = create_app()
    app.run(host="0.0.0.0", port=config.PORT, debug=False, use_reloader=False)


def main():
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

    db.init_db()
    ensure_persian_font()

    # Flask admin panel runs in a background thread so the bot's polling loop can own the main thread.
    threading.Thread(target=run_admin_panel, daemon=True).start()

    application = build_application()
    logger.info("Bot starting (polling mode)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
