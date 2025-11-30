import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_pdf_to_drive(local_path: str, filename: str) -> str:
    """
    Sube un PDF a Google Drive usando OAuth2 (client_id + client_secret + refresh_token).
    Devuelve la URL pública del archivo.
    """

    CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN")
    FOLDER_NAME = os.environ.get("GOOGLE_DRIVE_FOLDER_NAME", "FacturasAFIP")

    if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN:
        raise Exception("Faltan variables OAuth en Render")

    # 1) Credenciales OAuth2
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )

    # 2) Servicio de Google Drive
    service = build("drive", "v3", credentials=creds)

    # 3) Buscar carpeta (o crearla si no existe)
    query = f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder'"
    res = service.files().list(q=query, spaces="drive").execute()

    if res.get("files"):
        folder_id = res["files"][0]["id"]
    else:
        folder_metadata = {
            "name": FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
        }
        folder = service.files().create(body=folder_metadata, fields="id").execute()
        folder_id = folder["id"]

    # 4) Subir el archivo
    file_metadata = {
        "name": filename,
        "parents": [folder_id]
    }

    media = MediaFileUpload(local_path, mimetype="application/pdf")

    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    file_id = uploaded["id"]

    # 5) Hacer el archivo público (ANYONE WITH LINK)
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    # 6) URL Pública final
    public_url = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"

    return public_url

