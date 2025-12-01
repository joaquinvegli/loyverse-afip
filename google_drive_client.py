import os
import json
import io
from typing import Tuple, Dict, Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_drive_service():
    """
    Autenticación OAuth2 usando:
    - GOOGLE_CLIENT_ID
    - GOOGLE_CLIENT_SECRET
    - GOOGLE_REFRESH_TOKEN

    Esto permite subir y descargar archivos del Drive PERSONAL del usuario.
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


# ============================================================
# 1) SUBIR PDF (lo que ya tenías) — SIN CAMBIOS
# ============================================================
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


# ============================================================
# 2) HELPERS PARA facturas_db.json
# ============================================================
def _get_facturas_db_file_id(service) -> str | None:
    """
    Obtiene el ID del archivo facturas_db.json en Drive.

    Prioridad:
    1) FACTURAS_DB_FILE_ID (env var)
    2) Buscar por nombre 'facturas_db.json' dentro de GOOGLE_DRIVE_FOLDER_ID
    """
    env_id = os.environ.get("FACTURAS_DB_FILE_ID")
    if env_id:
        return env_id

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise RuntimeError("Falta GOOGLE_DRIVE_FOLDER_ID en variables de entorno")

    # Buscar el archivo por nombre dentro de la carpeta
    query = (
        f"name = 'facturas_db.json' and "
        f"'{folder_id}' in parents and "
        f"trashed = false"
    )

    results = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
            pageSize=1,
        )
        .execute()
    )

    files = results.get("files", [])
    if files:
        return files[0]["id"]

    return None


# ============================================================
# 3) DESCARGAR facturas_db.json DESDE DRIVE
# ============================================================
def download_facturas_db(local_path: str = "facturas_db.json") -> Dict[str, Any]:
    """
    Descarga facturas_db.json desde Google Drive y lo guarda en local_path.
    Devuelve el dict cargado desde el JSON.

    Si el archivo no existe en Drive, crea uno vacío ({}) en Drive
    y también localmente.
    """
    service = get_drive_service()

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise RuntimeError("Falta GOOGLE_DRIVE_FOLDER_ID en variables de entorno")

    file_id = _get_facturas_db_file_id(service)

    # Si no existe en Drive, lo creamos con contenido vacío {}
    if not file_id:
        # Crear archivo vacío en local
        data: Dict[str, Any] = {}
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        media = MediaFileUpload(local_path, mimetype="application/json")

        file_metadata = {
            "name": "facturas_db.json",
            "parents": [folder_id],
        }

        created = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        # NOTA: aunque obtengamos el nuevo ID, no podemos setear la env var desde el código.
        # En próximas ejecuciones, si FACTURAS_DB_FILE_ID no está, se buscará por nombre.
        file_id = created.get("id")
        return data

    # Si existe en Drive, lo descargamos
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    fh.seek(0)

    try:
        text = fh.read().decode("utf-8")
        data = json.loads(text or "{}")
    except Exception:
        data = {}

    # Guardar también en disco local
    try:
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        # Si falla el guardado local, igual devolvemos el dict
        pass

    return data


# ============================================================
# 4) SUBIR facturas_db.json A DRIVE
# ============================================================
def upload_facturas_db(local_path: str = "facturas_db.json") -> None:
    """
    Sube el archivo local facturas_db.json a Google Drive.

    - Si FACTURAS_DB_FILE_ID existe o se encuentra el archivo por nombre:
        → se hace un update sobre ese archivo.
    - Si no existe:
        → se crea uno nuevo dentro de GOOGLE_DRIVE_FOLDER_ID.
    """
    if not os.path.exists(local_path):
        # Nada que subir
        return

    service = get_drive_service()

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise RuntimeError("Falta GOOGLE_DRIVE_FOLDER_ID en variables de entorno")

    file_id = _get_facturas_db_file_id(service)

    media = MediaFileUpload(local_path, mimetype="application/json")

    if file_id:
        # Actualizar archivo existente
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        # Crear nuevo archivo en la carpeta
        file_metadata = {
            "name": "facturas_db.json",
            "parents": [folder_id],
        }
        service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()
