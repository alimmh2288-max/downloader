"""
DyReXR Backend
==============
هذا السيرفر يلعب دور "مزود Cobalt الخاص" اللي كود الفرونت إند (index.html)
يبحث عنه في CONFIG.COBALT_ENDPOINT.

الشكل اللي يرجعه متوافق 100% مع دالة downloadWithCobalt() الموجودة عندك:
- نجاح فيديو/صوت واحد:   {"status": "success", "url": "..."}
- نتائج متعددة (كاروسيل): {"status": "picker", "picker": [{"url": "...", "type": "video|photo|audio"}]}

يدعم: يوتيوب، إنستقرام، فيسبوك (أي منصة يدعمها yt-dlp أصلاً).
لا علاقة له بـ TikTok أو X — هذولا already شغالين بموصلاتهم المستقلة في الفرونت إند.
"""

import os
import uuid
import shutil
import logging
import threading
import time

import yt_dlp
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dyrexr-backend")

# =========================================================
# إعدادات
# =========================================================

# دومين السيرفر نفسه (يُستخدم لبناء روابط /files/... اللي نرجعها للفرونت إند).
# لازم تحطه بعد ما تنشر السيرفر، مثال: https://dyrexr-api.onrender.com
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")

# مفتاح سري بسيط (اختياري) لمنع أي شخص عشوائي من استخدام سيرفرك.
# لو تركته فاضي، ما فيه حماية. أفضل تحطه وتضيف نفس القيمة في الفرونت إند.
API_KEY = os.environ.get("API_KEY", "")

# مجلد مؤقت لحفظ الملفات قبل تسليمها للمستخدم
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ملف كوكيز اختياري لتجاوز رسالة يوتيوب "Sign in to confirm you're not a bot".
# إذا رفعت الملف كـ Secret File باسم cookies.txt في Render، بيُقرأ تلقائيًا من هنا.
COOKIES_PATH = "/etc/secrets/cookies.txt"

# أقصى عمر للملف المؤقت بالثواني (تنظيف تلقائي حتى لو ما تحمل المستخدم الملف)
MAX_FILE_AGE_SECONDS = 30 * 60  # 30 دقيقة

app = FastAPI(title="DyReXR Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # في الإنتاج يفضل تحطها = دومين تطبيقك فقط
    allow_methods=["*"],
    allow_headers=["*"],
)


class DownloadRequest(BaseModel):
    url: str
    videoQuality: str = "max"
    audioFormat: str = "mp3"
    downloadMode: str = "auto"   # "auto" (فيديو) أو "audio"
    filenameStyle: str = "pretty"
    apiKey: str | None = None


# =========================================================
# تنظيف الملفات القديمة تلقائيًا (تعمل في الخلفية عند تشغيل السيرفر)
# =========================================================

def _cleanup_loop():
    while True:
        now = time.time()
        try:
            for name in os.listdir(DOWNLOAD_DIR):
                path = os.path.join(DOWNLOAD_DIR, name)
                if os.path.isfile(path) and now - os.path.getmtime(path) > MAX_FILE_AGE_SECONDS:
                    os.remove(path)
        except Exception as e:
            log.warning("cleanup error: %s", e)
        time.sleep(300)


threading.Thread(target=_cleanup_loop, daemon=True).start()


def _delete_later(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


# =========================================================
# المسار الرئيسي: نفس شكل Cobalt اللي الفرونت إند يتوقعه
# =========================================================

@app.post("/api")
def resolve(payload: DownloadRequest, background_tasks: BackgroundTasks):
    if API_KEY and payload.apiKey != API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")

    audio_only = payload.downloadMode == "audio"
    file_id = uuid.uuid4().hex

    out_template = os.path.join(DOWNLOAD_DIR, f"{file_id}_%(playlist_index)s.%(ext)s")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,          # منشور واحد فقط، مو قائمة تشغيل كاملة
        "outtmpl": out_template,
        "restrictfilenames": True,
        "format": "bestaudio/best" if audio_only else "bestvideo+bestaudio/best",
    }

    if not audio_only:
        ydl_opts["merge_output_format"] = "mp4"

    if audio_only:
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    if os.path.exists(COOKIES_PATH):
        ydl_opts["cookiefile"] = COOKIES_PATH

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(payload.url, download=True)

            entries = info.get("entries")

            # حالة: منشور فيه أكثر من ملف (كاروسيل إنستقرام مثلاً) -> picker
            if entries:
                picker = []
                for entry in entries:
                    if entry is None:
                        continue
                    fname = ydl.prepare_filename(entry)
                    if audio_only:
                        fname = os.path.splitext(fname)[0] + ".mp3"
                    if os.path.exists(fname):
                        token = os.path.basename(fname)
                        background_tasks.add_task(
                            lambda p=os.path.join(DOWNLOAD_DIR, token): None
                        )  # الحذف الفعلي يصير بعد ما يفتح المستخدم /files/token (أدناه)
                        media_type = "audio" if audio_only else (
                            "photo" if entry.get("vcodec") in (None, "none") else "video"
                        )
                        picker.append({
                            "url": f"{BASE_URL}/files/{token}",
                            "type": media_type,
                        })

                if not picker:
                    raise HTTPException(status_code=404, detail="no_media_found")

                return {"status": "picker", "picker": picker}

            # حالة: ملف واحد
            fname = ydl.prepare_filename(info)
            if audio_only:
                fname = os.path.splitext(fname)[0] + ".mp3"

            if not os.path.exists(fname):
                raise HTTPException(status_code=404, detail="file_missing_after_download")

            token = os.path.basename(fname)
            return {"status": "success", "url": f"{BASE_URL}/files/{token}"}

    except HTTPException:
        raise
    except Exception as e:
        log.exception("extraction failed")
        raise HTTPException(status_code=502, detail=f"provider_error: {e}")


@app.get("/files/{token}")
def get_file(token: str, background_tasks: BackgroundTasks):
    # حماية بسيطة من مسارات غريبة
    safe_token = os.path.basename(token)
    path = os.path.join(DOWNLOAD_DIR, safe_token)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="not_found")

    background_tasks.add_task(_delete_later, path)
    return FileResponse(path, filename=safe_token)


@app.get("/health")
def health():
    return {"ok": True}
