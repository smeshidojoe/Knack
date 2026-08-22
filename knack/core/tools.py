"""
Внешние бинарники: пока только ffmpeg.

Лежит в %APPDATA%\\Knack\\tools и качается по требованию — когда на полку
впервые попадает видео или музыка и нужно превью. В сборку его не кладём:
восемьдесят мегабайт ради одной картинки на карточке того не стоят, а нужен он
далеко не каждому.

Сборка BtbN: у неё стабильные имена ассетов и нет зависимостей от системных
библиотек.
"""

import io
import os
import subprocess
import zipfile

from .constants import APP_DIR

TOOLS_DIR = os.path.join(APP_DIR, "tools")
FFMPEG_EXE = os.path.join(TOOLS_DIR, "ffmpeg.exe")

# Датированные релизы содержат git-хеш в имени, поэтому ссылку резолвим через
# API; latest — запасной вариант, если API недоступен.
FFMPEG_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases?per_page=20"
FFMPEG_ZIP = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
              "ffmpeg-master-latest-win64-gpl.zip")

CREATE_NO_WINDOW = 0x08000000     # чтобы не мигало консольное окно


def have_ffmpeg():
    return os.path.isfile(FFMPEG_EXE)


def _ssl_context():
    import ssl
    context = ssl.create_default_context()
    try:
        import certifi
        context.load_verify_locations(certifi.where())
    except Exception:
        pass
    return context


def _ffmpeg_url():
    import json
    import urllib.request
    try:
        request = urllib.request.Request(
            FFMPEG_API, headers={"User-Agent": "Knack",
                                 "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=30,
                                    context=_ssl_context()) as response:
            releases = json.load(response)
        for release in releases:
            if release.get("tag_name") == "latest":
                continue
            for asset in release.get("assets", []):
                name = asset.get("name", "")
                if name.endswith("win64-gpl-7.1.zip") and "shared" not in name:
                    return asset.get("browser_download_url")
    except Exception:
        pass
    return FFMPEG_ZIP


def download_ffmpeg(on_progress=None, timeout=180):
    """Качает и распаковывает ffmpeg.exe. Ошибки пробрасывает наверх."""
    import urllib.request
    os.makedirs(TOOLS_DIR, exist_ok=True)
    request = urllib.request.Request(_ffmpeg_url(),
                                     headers={"User-Agent": "Knack"})
    buffer = io.BytesIO()
    with urllib.request.urlopen(request, timeout=timeout,
                                context=_ssl_context()) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            buffer.write(chunk)
            done += len(chunk)
            if on_progress and total:
                on_progress(done / total)

    with zipfile.ZipFile(buffer) as archive:
        for name in archive.namelist():
            # ffprobe не берём: длительность нам не нужна, а это ещё столько же
            # мегабайт на диске.
            if os.path.basename(name).lower() == "ffmpeg.exe":
                with archive.open(name) as src, open(FFMPEG_EXE, "wb") as dst:
                    dst.write(src.read())
                return True
    raise RuntimeError("в архиве нет ffmpeg.exe")


def run(args, timeout=25):
    """Запускает ffmpeg без консольного окна. True — код возврата ноль."""
    if not have_ffmpeg():
        return False
    try:
        result = subprocess.run([FFMPEG_EXE] + list(args),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=CREATE_NO_WINDOW,
                                timeout=timeout)
        return result.returncode == 0
    except Exception:
        return False
