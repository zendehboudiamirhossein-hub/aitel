import io
import zipfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import db
import utils
from handlers.chat import guard
from handlers.keyboards import zip_action_kb, build_main_menu

MAX_FILES_IN_SESSION = 30
MAX_ZIP_INPUT_MB = 20


# ------------------------------------------------------------------ /zip creation flow (button driven)

async def zip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    context.user_data["zip_collecting"] = []
    await update.message.reply_text(
        "🗜 حالت ساخت zip فعال شد.\n"
        "هر فایل یا عکسی که بفرستی به آرشیو اضافه میشه.\n"
        "وقتی تموم شد روی «پایان و دریافت آرشیو» بزن.",
        reply_markup=zip_action_kb(),
    )


def _build_zip_bytes(files):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        used_names = set()
        for f in files:
            name = f["name"]
            base = name
            i = 1
            while name in used_names:
                stem, dot, ext = base.rpartition(".")
                name = f"{stem or base}_{i}{dot}{ext}"
                i += 1
            used_names.add(name)
            zf.writestr(name, f["data"])
    bio.seek(0)
    return bio


async def zipsession_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    user_id = update.effective_user.id

    if action == "cancel":
        context.user_data.pop("zip_collecting", None)
        await query.edit_message_text("❌ ساخت zip لغو شد.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="منوی اصلی:",
                                        reply_markup=build_main_menu(user_id))
        return

    files = context.user_data.get("zip_collecting")
    if not files:
        await query.edit_message_text("هنوز فایلی اضافه نکردی. دوباره روی «🗜 ساخت Zip» بزن و چند فایل بفرست.")
        return

    bio = _build_zip_bytes(files)
    bio.name = "archive.zip"
    count = len(files)
    context.user_data.pop("zip_collecting", None)

    await query.edit_message_text(f"✅ آرشیو با {count} فایل آماده شد.")
    await context.bot.send_document(
        chat_id=query.message.chat_id, document=bio, filename="archive.zip",
        reply_markup=build_main_menu(user_id),
    )
    db.bump_counter(user_id, "file_count")


async def maybe_collect_for_zip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """If the user is in an active /zip session, absorb this document/photo. Returns True if consumed."""
    files = context.user_data.get("zip_collecting")
    if files is None:
        return False
    if len(files) >= MAX_FILES_IN_SESSION:
        await update.message.reply_text(
            f"حداکثر {MAX_FILES_IN_SESSION} فایل در هر آرشیو مجاز است.",
            reply_markup=zip_action_kb(),
        )
        return True

    if update.message.document:
        tg_file = await context.bot.get_file(update.message.document.file_id)
        name = update.message.document.file_name or f"file_{len(files)+1}"
    elif update.message.photo:
        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        name = f"photo_{len(files)+1}.jpg"
    else:
        return False

    data = await tg_file.download_as_bytearray()
    files.append({"name": utils.safe_filename(name), "data": bytes(data)})
    await update.message.reply_text(
        f"➕ اضافه شد ({len(files)} فایل تا الان). ادامه بده یا پایان بده:",
        reply_markup=zip_action_kb(),
    )
    return True


# ------------------------------------------------------------------ editing an uploaded .zip

def _is_zip_document(document) -> bool:
    if not document:
        return False
    name = (document.file_name or "").lower()
    return name.endswith(".zip") or document.mime_type in (
        "application/zip", "application/x-zip-compressed"
    )


async def handle_incoming_zip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """If the document is a zip file, store it and show the edit menu. Returns True if handled."""
    document = update.message.document
    if not _is_zip_document(document):
        return False

    if document.file_size and document.file_size > MAX_ZIP_INPUT_MB * 1024 * 1024:
        await update.message.reply_text(f"این فایل zip خیلی بزرگه (بیشتر از {MAX_ZIP_INPUT_MB}MB).")
        return True

    # if we're waiting to ADD this zip's sibling file into an already-open zip session, handle separately
    if context.user_data.get("zip_add_target"):
        return await _add_file_to_open_zip(update, context)

    tg_file = await context.bot.get_file(document.file_id)
    data = await tg_file.download_as_bytearray()
    context.user_data["edit_zip"] = {"name": document.file_name or "archive.zip", "data": bytes(data)}

    try:
        with zipfile.ZipFile(io.BytesIO(bytes(data))) as zf:
            count = len(zf.namelist())
    except zipfile.BadZipFile:
        await update.message.reply_text("❌ این فایل یک zip معتبر نیست.")
        return True

    buttons = [
        [InlineKeyboardButton("📋 لیست فایل‌ها", callback_data="zip:list")],
        [InlineKeyboardButton("📤 استخراج و ارسال همه فایل‌ها", callback_data="zip:extract")],
        [InlineKeyboardButton("➕ افزودن فایل به آرشیو", callback_data="zip:addmode")],
        [InlineKeyboardButton("🗑 حذف یک فایل از آرشیو", callback_data="zip:removemenu:0")],
    ]
    await update.message.reply_text(
        f"📦 فایل zip دریافت شد ({count} مورد داخلش هست). چیکار کنم؟",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return True


async def zip_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get("edit_zip")
    if not data:
        await query.edit_message_text("این آرشیو دیگه در دسترس نیست. یک فایل zip جدید بفرست.")
        return

    action_parts = query.data.split(":")
    action = action_parts[1]

    if action == "list":
        with zipfile.ZipFile(io.BytesIO(data["data"])) as zf:
            names = zf.namelist()
        text = "📋 محتویات آرشیو:\n" + "\n".join(f"• {n}" for n in names[:200])
        if len(names) > 200:
            text += f"\n... و {len(names) - 200} مورد دیگر"
        await query.message.reply_text(text)

    elif action == "extract":
        with zipfile.ZipFile(io.BytesIO(data["data"])) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            for n in names[:20]:
                content = zf.read(n)
                if len(content) > 45 * 1024 * 1024:
                    continue
                bio = io.BytesIO(content)
                bio.name = n.split("/")[-1] or "file"
                await query.message.reply_document(document=bio, filename=bio.name)
            if len(names) > 20:
                await query.message.reply_text(f"فقط ۲۰ فایل اول ارسال شد (مجموع {len(names)} فایل بود).")

    elif action == "addmode":
        context.user_data["zip_add_target"] = True
        await query.message.reply_text("📎 حالا فایلی که می‌خوای به آرشیو اضافه بشه رو بفرست.")

    elif action == "removemenu":
        page = int(action_parts[2]) if len(action_parts) > 2 else 0
        with zipfile.ZipFile(io.BytesIO(data["data"])) as zf:
            names = zf.namelist()
        page_size = 8
        page_names = names[page * page_size:(page + 1) * page_size]
        if not page_names:
            await query.message.reply_text("فایلی برای حذف باقی نمونده.")
            return
        buttons = [[InlineKeyboardButton(f"🗑 {n}", callback_data=f"zip:rm:{n}")] for n in page_names]
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"zip:removemenu:{page-1}"))
        if (page + 1) * page_size < len(names):
            nav.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"zip:removemenu:{page+1}"))
        if nav:
            buttons.append(nav)
        await query.message.reply_text("کدوم فایل حذف بشه؟", reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "rm":
        target = query.data.split(":", 2)[2]
        new_bio = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data["data"])) as zf_in, \
                zipfile.ZipFile(new_bio, "w", zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                if item.filename != target:
                    zf_out.writestr(item, zf_in.read(item.filename))
        context.user_data["edit_zip"]["data"] = new_bio.getvalue()
        new_bio.seek(0)
        new_bio.name = data["name"]
        await query.message.reply_text(f"✅ «{target}» حذف شد. آرشیو به‌روزشده:")
        await query.message.reply_document(document=new_bio, filename=data["name"])


async def _add_file_to_open_zip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    edit_zip = context.user_data.get("edit_zip")
    if not edit_zip:
        context.user_data.pop("zip_add_target", None)
        return False

    document = update.message.document
    tg_file = await context.bot.get_file(document.file_id)
    file_bytes = bytes(await tg_file.download_as_bytearray())
    name = utils.safe_filename(document.file_name or "file")

    new_bio = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(edit_zip["data"])) as zf_in, \
            zipfile.ZipFile(new_bio, "w", zipfile.ZIP_DEFLATED) as zf_out:
        for item in zf_in.infolist():
            zf_out.writestr(item, zf_in.read(item.filename))
        zf_out.writestr(name, file_bytes)

    context.user_data["edit_zip"]["data"] = new_bio.getvalue()
    context.user_data.pop("zip_add_target", None)

    new_bio.seek(0)
    new_bio.name = edit_zip["name"]
    await update.message.reply_text(f"✅ «{name}» به آرشیو اضافه شد. آرشیو به‌روزشده:")
    await update.message.reply_document(document=new_bio, filename=edit_zip["name"])
    return True


async def handle_document_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Single entry point registered on the Document filter; dispatches to the right zip flow,
    otherwise falls through to file-related hints."""
    if not await guard(update):
        return

    if context.user_data.get("zip_add_target") and update.message.document \
            and not _is_zip_document(update.message.document):
        if await _add_file_to_open_zip(update, context):
            return

    if await maybe_collect_for_zip(update, context):
        return

    if await handle_incoming_zip(update, context):
        return

    await update.message.reply_text(
        "این فایل رو دریافت کردم ولی نمی‌دونم باهاش چیکار کنی 🙂\n"
        "اگه می‌خوای چند فایل رو zip کنی، اول از دکمه «🗜 ساخت Zip» استفاده کن.\n"
        "اگه فایل zip بفرستی، می‌تونم محتوایش رو نشونت بدم یا ویرایشش کنم."
    )


async def handle_photo_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await maybe_collect_for_zip(update, context)
