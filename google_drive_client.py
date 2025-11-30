import os
from typing import Tuple

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_drive_service():
    """
    Autenticación OAuth2 usando:
    - GOOGLE_CLIENT_ID
    - GOOGLE_CLIENT_SECRET
    - GOOGLE_REFRESH_TOKEN
    Esto permite subir archivos al Drive PERSONAL del usuario.
    """

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token:
        raise RuntimeError(
            "Faltan variables OAuth2: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN"
        )

    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    service = build("drive", "v3", credentials=creds)
    return service



def upload_pdf_to_drive(local_pdf_path: str, pdf_name: str) -> Tuple[str, str]:
    """
    Sube un PDF usando OAuth2 a la carpeta especificada.
    Devuelve (file_id, public_url)
    """

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise RuntimeError("Falta GOOGLE_DRIVE_FOLDER_ID en variables de entorno")

    service = get_drive_service()

    # Metadatos del archivo
    file_metadata = {
        "name": pdf_name,
        "parents": [folder_id],
    }

    media = MediaFileUpload(local_pdf_path, mimetype="application/pdf")

    # Crear archivo en Drive
    created = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )

    file_id = created.get("id")

    # Hacerlo público por link
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
        fields="id",
    ).execute()

    public_url = f"https://drive.google.com/uc?id={file_id}&export=download"

    return file_id, public_url
