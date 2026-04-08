import base64
import binascii
from email.message import EmailMessage
from email.utils import formataddr

from fastapi import HTTPException, status
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings

_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _build_gmail_service(sender_email: str):
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=_GMAIL_SCOPES,
    )
    delegated_creds = creds.with_subject(sender_email)
    return build("gmail", "v1", credentials=delegated_creds, cache_discovery=False)


def decode_pdf_base64(raw_value: str) -> bytes:
    value = (raw_value or "").strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se recibio el PDF.")

    if value.startswith("data:"):
        parts = value.split(",", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Formato base64 invalido.")
        value = parts[1]

    try:
        pdf_bytes = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El PDF no tiene un base64 valido.") from exc

    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo adjunto no parece ser un PDF valido.")

    if len(pdf_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El PDF excede el tamano permitido.")

    return pdf_bytes


def send_email_with_pdf(
    *,
    sender_email: str,
    sender_name: str,
    to_email: str,
    subject: str,
    body: str,
    pdf_filename: str,
    pdf_bytes: bytes,
) -> str:
    message = EmailMessage()
    message["To"] = to_email
    message["From"] = formataddr((sender_name, sender_email))
    message["Subject"] = subject
    message.set_content(body)
    message.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=pdf_filename)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    try:
        service = _build_gmail_service(sender_email)
        response = service.users().messages().send(
            userId="me",
            body={"raw": raw_message},
        ).execute()
        return response["id"]
    except HttpError as exc:
        reason = exc._get_reason() if hasattr(exc, "_get_reason") else str(exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo enviar el correo con Gmail: {reason}",
        ) from exc
