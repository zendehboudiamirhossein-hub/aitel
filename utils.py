import os
import re
import requests

import config

TELEGRAM_MAX_LEN = 4000

FONT_CANDIDATE_URLS = [
    "https://github.com/rastikerdar/vazirmatn/raw/master/fonts/ttf/Vazirmatn-Regular.ttf",
    "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Regular.ttf",
]


def ensure_persian_font():
    """Best-effort download of a Persian/Arabic capable TTF font used for PDF export.
    Falls back silently (PDF code will use a Latin-only font) if the download fails,
    e.g. because outbound network access is restricted on the host."""
    if os.path.exists(config.FONT_PATH):
        return config.FONT_PATH
    os.makedirs(os.path.dirname(config.FONT_PATH), exist_ok=True)
    for url in FONT_CANDIDATE_URLS:
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200 and len(resp.content) > 10000:
                with open(config.FONT_PATH, "wb") as f:
                    f.write(resp.content)
                return config.FONT_PATH
        except Exception:
            continue
    return None


def split_message(text, limit=TELEGRAM_MAX_LEN):
    """Split long text into Telegram-safe chunks, preferring paragraph/line breaks."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:]
    if text:
        chunks.append(text)
    return chunks


def safe_filename(name, default="file"):
    name = (name or default).strip()
    name = re.sub(r"[^\w\-. آ-یءئؤًٌٍَُِّْٰٓٔٱ]+", "_", name, flags=re.UNICODE)
    return name[:80] or default


def contains_persian(text):
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))
