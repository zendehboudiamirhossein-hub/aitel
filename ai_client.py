"""
Thin wrapper around the AnyModel.org OpenAI-compatible API.
Docs: https://anymodel.org/en  (base URL https://anymodel.org/v1)
"""
import base64
import requests

import config
import db

TIMEOUT = 120


def _headers(extra=None):
    h = {"Authorization": f"Bearer {config.ANYMODEL_API_KEY}"}
    if extra:
        h.update(extra)
    return h


class AnyModelError(Exception):
    pass


def chat_completion(messages, model=None, temperature=0.7):
    """messages: list of {"role": "system"|"user"|"assistant", "content": str}"""
    model = model or config.ANYMODEL_CHAT_MODEL
    url = f"{config.ANYMODEL_BASE_URL}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    try:
        resp = requests.post(url, headers=_headers({"Content-Type": "application/json"}),
                              json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        db.log_event("error", f"chat_completion failed: {e}")
        raise AnyModelError(f"AI request failed: {e}")


def generate_image(prompt, model=None, size="1024x1024", n=1):
    """Returns a list of raw image bytes."""
    model = model or config.ANYMODEL_IMAGE_MODEL
    url = f"{config.ANYMODEL_BASE_URL}/images/generations"
    payload = {"model": model, "prompt": prompt, "size": size, "n": n}
    try:
        resp = requests.post(url, headers=_headers({"Content-Type": "application/json"}),
                              json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        images = []
        for item in data.get("data", []):
            if item.get("b64_json"):
                images.append(base64.b64decode(item["b64_json"]))
            elif item.get("url"):
                img_resp = requests.get(item["url"], timeout=TIMEOUT)
                img_resp.raise_for_status()
                images.append(img_resp.content)
        if not images:
            raise AnyModelError("No image returned by AnyModel")
        return images
    except AnyModelError:
        raise
    except Exception as e:
        db.log_event("error", f"generate_image failed: {e}")
        raise AnyModelError(f"Image generation failed: {e}")


def transcribe_audio(file_path, model=None, language=None):
    """Speech-to-text. Returns transcribed text."""
    model = model or config.ANYMODEL_STT_MODEL
    url = f"{config.ANYMODEL_BASE_URL}/audio/transcriptions"
    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, "application/octet-stream")}
            data = {"model": model}
            if language:
                data["language"] = language
            resp = requests.post(url, headers=_headers(), files=files, data=data, timeout=TIMEOUT)
        resp.raise_for_status()
        result = resp.json()
        return result.get("text", "")
    except Exception as e:
        db.log_event("error", f"transcribe_audio failed: {e}")
        raise AnyModelError(f"Transcription failed: {e}")


def text_to_speech(text, model=None, voice=None):
    """Returns raw audio bytes (mp3/ogg depending on API)."""
    model = model or config.ANYMODEL_TTS_MODEL
    voice = voice or config.ANYMODEL_TTS_VOICE
    url = f"{config.ANYMODEL_BASE_URL}/audio/speech"
    payload = {"model": model, "input": text, "voice": voice}
    try:
        resp = requests.post(url, headers=_headers({"Content-Type": "application/json"}),
                              json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        db.log_event("error", f"text_to_speech failed: {e}")
        raise AnyModelError(f"Text-to-speech failed: {e}")
