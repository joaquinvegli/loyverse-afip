# google_drive_client.py
import os
import json
import time
from typing import Tuple, Dict, Any

import httpx
from supabase import create_client, Client

# ============================================================
# CONFIGURACIÓN SUPABASE
# ============================================================
def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY en variables de entorno")
    return create_client(url, key)

SUPABASE_BUCKET = "facturas"
FACTURAS_DB_PATH = "db/facturas_db.json"


# ============================================================
# 1) SUBIR PDF
# ============================================================
def upload_pdf_to_drive(local_pdf_path: str, pdf_name: str) -> Tuple[str, str]:
    supabase = get_supabase()

    with open(local_pdf_path, "rb") as f:
        pdf_bytes = f.read()

    path_en_bucket = f"pdfs/{pdf_name}"

    supabase.storage.from_(SUPABASE_BUCKET).upload(
        path=path_en_bucket,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )

    url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(path_en_bucket)

    return path_en_bucket, url


# ============================================================
# 2) DESCARGAR JSON DE FACTURAS
# ============================================================
def download_facturas_db(local_path: str = "facturas_db.json") -> Dict[str, Any]:
    try:
        supabase = get_supabase()

        url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(FACTURAS_DB_PATH)

        # Timestamp para evitar caché
        url_sin_cache = f"{url}?t={int(time.time())}"

        r = httpx.get(url_sin_cache, timeout=15, follow_redirects=True)

        # Si no existe todavía devuelve 400 o 404
        if r.status_code in (400, 404):
            print("DEBUG → facturas_db.json no existe en Supabase todavía")
            return {}

        r.raise_for_status()

        content = r.text.strip()
        print(f"DEBUG → Supabase DB status: {r.status_code}, length: {len(content)}, inicio: {content[:100]}")

        if not content:
            print("DEBUG → Supabase devolvió contenido vacío")
            return {}

        data = json.loads(content)

        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return data

    except json.JSONDecodeError as e:
        print(f"⚠️ Error parseando JSON desde Supabase: {e}")
        return {}
    except Exception as e:
        print(f"⚠️ Error descargando facturas_db desde Supabase: {e}")
        return {}


# ============================================================
# 3) SUBIR JSON DE FACTURAS
# ============================================================
def upload_facturas_db(local_path: str = "facturas_db.json") -> None:
    if not os.path.exists(local_path):
        print("DEBUG → No existe facturas_db.json local para subir")
        return

    try:
        supabase = get_supabase()

        with open(local_path, "rb") as f:
            json_bytes = f.read()

        supabase.storage.from_(SUPABASE_BUCKET).upload(
            path=FACTURAS_DB_PATH,
            file=json_bytes,
            file_options={"content-type": "application/json", "upsert": "true"},
        )

        print("DEBUG → facturas_db.json subido a Supabase correctamente")

    except Exception as e:
        print(f"⚠️ Error subiendo facturas_db a Supabase: {e}")
```

También podés sacar `cloudinary` del `requirements.txt` ya que no lo usamos más. Reemplazalo con:
```
fastapi
uvicorn
httpx
python-multipart
requests
git+https://github.com/reingart/pyafipws.git#egg=pyafipws
reportlab
qrcode
Pillow
supabase
