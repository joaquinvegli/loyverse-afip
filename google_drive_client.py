import os
import json
import base64
from typing import Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Alcance mínimo para manipular archivos de Drive
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_drive_service():
    """
    Crea un cliente autenticado de Google Drive usando
    las credenciales del service account en la env var
    GOOGLE_SERVICE_ACCOUNT_JSON.
    """
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("Falta GOOGLE_SERVICE_ACCOUNT_JSON en variables de entorno")

    info = json.loads(raw)

    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=SCOPES
    )

    service = build("drive", "v3", credentials=creds)
    return service


def upload_pdf_to_drive(local_pdf_path: str, receipt_id: str) -> Tuple[str, str]:
    """
    Sube un PDF a la carpeta de Drive definida por GOOGLE_DRIVE_FOLDER_ID.
    Devuelve (file_id, public_url)
    """
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise RuntimeError("Falta GOOGLE_DRIVE_FOLDER_ID en variables de entorno")

    service = get_drive_service()

    file_metadata = {
        "name": f"Factura_{receipt_id}.pdf",
        "parents": [folder_id],
    }

    media = MediaFileUpload(local_pdf_path, mimetype="application/pdf")

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    file_id = file.get("id")

    # Hacer el archivo accesible por link (cualquiera con el enlace)
    service.permissions().create(
        fileId=file_id,
        body={
            "role": "reader",
            "type": "anyone"
        }
    ).execute()

    public_url = f"https://drive.google.com/uc?id={file_id}&export=download"

    return file_id, public_url
