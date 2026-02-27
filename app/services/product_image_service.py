import io
import re
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image

from app.core.config import settings


_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def extract_drive_file_id(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        raise ValueError("La URL de imagen está vacía.")

    patterns = [
        r"/file/d/([^/]+)",
        r"[?&]id=([^&]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, url, flags=re.IGNORECASE)
        if match and match.group(1):
            return match.group(1)

    raise ValueError("No se pudo extraer el fileId desde la URL de Google Drive.")


def _build_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=_DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def download_drive_file(file_id: str) -> bytes:
    service = _build_drive_service()

    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    buffer.seek(0)
    return buffer.read()


def resize_image_to_box(raw_bytes: bytes, width: int = 140, height: int = 90) -> bytes:
    src = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")

    # Mantiene proporción; nunca deforma
    src.thumbnail((width, height), Image.Resampling.LANCZOS)

    # Fondo blanco fijo 140x90
    canvas = Image.new("RGB", (width, height), (255, 255, 255))

    x = (width - src.width) // 2
    y = (height - src.height) // 2

    # Si la imagen tiene transparencia, la respeta al pegar
    if "A" in src.getbands():
        canvas.paste(src.convert("RGB"), (x, y), src.getchannel("A"))
    else:
        canvas.paste(src.convert("RGB"), (x, y))

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=90, optimize=True)
    out.seek(0)
    return out.read()


def build_product_thumbnail_from_drive_url(
    drive_url: str,
    width: int = 140,
    height: int = 90,
) -> bytes:
    file_id = extract_drive_file_id(drive_url)
    original_bytes = download_drive_file(file_id)
    return resize_image_to_box(original_bytes, width=width, height=height)