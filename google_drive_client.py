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
# 1) SUBIR PDF (sin cambios)
# ============================================================
def upload_pdf_to_drive(local_pdf_path: str, pdf_name: str) -> Tuple[str, str]:

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise RuntimeError("Falta GOOGLE_DRIVE_FOLDER_ID en variables de entorno")

    service = get_drive_service()

    file_metadata = {
        "name": pdf_name,
        "parents": [folder_id],
    }

    media = MediaFileUpload(local_pdf_path, mimetype="application/pdf")

    created = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )

    file_id = created.get("id")

    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
        fields="id",
    ).execute()

    public_url = f"https://drive.google.com/uc?id={file_id}&export=download"

    return file_id, public_url


# ============================================================
# 2) BUSCAR EL ID DEL JSON EN DRIVE
# ============================================================
def _get_facturas_db_file_id(service) -> str | None:

    env_id = os.environ.get("FACTURAS_DB_FILE_ID")
    if env_id:
        env_id = env_id.strip()   # ← eliminar espacios / saltos invisibles
        print("DEBUG → FACTURAS_DB_FILE_ID desde ENV =", repr(env_id))
        return env_id

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    folder_id = folder_id.strip()

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
        print("DEBUG → Encontrado facturas_db.json en Drive con ID =", files[0]["id"])
        return files[0]["id"]

    print("DEBUG → NO se encontró facturas_db.json en Drive")
    return None


# ============================================================
# 3) DESCARGAR JSON
# ============================================================
def download_facturas_db(local_path: str = "facturas_db.json") -> Dict[str, Any]:

    service = get_drive_service()

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        raise RuntimeError("Falta GOOGLE_DRIVE_FOLDER_ID")

    file_id = _get_facturas_db_file_id(service)
    print("DEBUG → Descargando JSON con file_id =", repr(file_id))

    # NO EXISTE → crear nuevo
    if not file_id:
        print("DEBUG → Creando facturas_db.json vacío en Drive")
        data = {}
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

        print("DEBUG → Nuevo ID creado =", created.get("id"))
        return data

    # EXISTE → descargar
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        fh.seek(0)
        data = json.loads(fh.read().decode("utf-8") or "{}")
    except Exception as e:
        print("⚠️ Error descargando facturas_db.json desde Drive:", e)
        return {}

    # guardar también en disco
    try:
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except:
        pass

    return data


# ============================================================
# 4) SUBIR JSON
# ============================================================
def upload_facturas_db(local_path: str = "facturas_db.json") -> None:

    if not os.path.exists(local_path):
        print("DEBUG → No existe facturas_db.json local para subir")
        return

    service = get_drive_service()

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        raise RuntimeError("Falta GOOGLE_DRIVE_FOLDER_ID")

    file_id = _get_facturas_db_file_id(service)
    print("DEBUG → Subiendo JSON con file_id =", repr(file_id))

    media = MediaFileUpload(local_path, mimetype="application/json")

    # UPDATE EXISTENTE
    if file_id:
        try:
            service.files().update(fileId=file_id, media_body=media).execute()
            print("DEBUG → JSON actualizado correctamente en Drive")
        except Exception as e:
            print("⚠️ Error subiendo facturas_db.json a Drive:", e)
        return

    # NO EXISTE → crear nuevo
    file_metadata = {
        "name": "facturas_db.json",
        "parents": [folder_id],
    }

    try:
        created = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )
        print("DEBUG → JSON creado nuevo en Drive con ID =", created.get("id"))
    except Exception as e:
        print("⚠️ Error creando nuevo facturas_db.json en Drive:", e)
