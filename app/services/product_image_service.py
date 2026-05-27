import io
import re
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image

from app.core.config import settings


_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PRODUCT_IMAGE_UPLOAD_DIR = _PROJECT_ROOT / "exports" / "product_images"
_UPLOADED_PRODUCT_IMAGE_PREFIX = "uploaded://product-images/"
_MAX_UPLOADED_IMAGE_BYTES = 8 * 1024 * 1024
_SUPPORTED_IMAGE_FORMATS = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
}


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


def is_uploaded_product_image_url(raw_url: str | None) -> bool:
    return str(raw_url or "").startswith(_UPLOADED_PRODUCT_IMAGE_PREFIX)


def _resolve_uploaded_product_image_path(raw_url: str) -> Path:
    filename = str(raw_url or "").removeprefix(_UPLOADED_PRODUCT_IMAGE_PREFIX)
    clean_name = Path(filename).name
    if not clean_name or clean_name != filename:
        raise ValueError("La ruta de imagen cargada no es valida.")

    return _PRODUCT_IMAGE_UPLOAD_DIR / clean_name


def read_uploaded_product_image(raw_url: str) -> bytes:
    path = _resolve_uploaded_product_image_path(raw_url)
    if not path.exists() or not path.is_file():
        raise ValueError("No se encontro la imagen cargada para este producto.")

    return path.read_bytes()


def build_product_thumbnail_from_uploaded_image_url(
    uploaded_url: str,
    width: int = 140,
    height: int = 90,
) -> bytes:
    return resize_image_to_box(
        read_uploaded_product_image(uploaded_url),
        width=width,
        height=height,
    )


def save_uploaded_product_image(product_id: int, raw_bytes: bytes) -> str:
    if not raw_bytes:
        raise ValueError("No se recibio ningun archivo de imagen.")

    if len(raw_bytes) > _MAX_UPLOADED_IMAGE_BYTES:
        raise ValueError("La imagen no puede superar 8 MB.")

    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.load()
    except Exception as exc:
        raise ValueError("El archivo seleccionado no es una imagen valida.") from exc

    image_format = str(image.format or "").upper()
    extension = _SUPPORTED_IMAGE_FORMATS.get(image_format)
    if not extension:
        raise ValueError("Solo se permiten imagenes JPG, PNG o WEBP.")

    _PRODUCT_IMAGE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for existing in _PRODUCT_IMAGE_UPLOAD_DIR.glob(f"product_{product_id}.*"):
        try:
            existing.unlink()
        except OSError:
            pass

    path = _PRODUCT_IMAGE_UPLOAD_DIR / f"product_{product_id}.{extension}"

    if image_format == "JPEG" and image.mode in {"RGBA", "LA", "P"}:
        canvas = Image.new("RGB", image.size, (255, 255, 255))
        alpha = image.getchannel("A") if "A" in image.getbands() else None
        canvas.paste(image.convert("RGB"), mask=alpha)
        image = canvas

    image.save(path, format=image_format, quality=92, optimize=True)
    return f"{_UPLOADED_PRODUCT_IMAGE_PREFIX}{path.name}"


def build_product_thumbnail_from_drive_url(
    drive_url: str,
    width: int = 140,
    height: int = 90,
) -> bytes:
    file_id = extract_drive_file_id(drive_url)
    original_bytes = download_drive_file(file_id)
    return resize_image_to_box(original_bytes, width=width, height=height)
