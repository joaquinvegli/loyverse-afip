# google_drive_client.py
import os
import json
import time
from typing import Tuple, Dict, Any

import cloudinary
import cloudinary.uploader
import cloudinary.api
import httpx

# ============================================================
# CONFIGURACIÓN CLOUDINARY
# ============================================================
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True,
)

FACTURAS_DB_PUBLIC_ID = "facturacion/facturas_db"


# ============================================================
# 1) SUBIR PDF
# ============================================================
def upload_pdf_to_drive(local_pdf_path: str, pdf_name: str) -> Tuple[str, str]:
    nombre_sin_ext = pdf_name.replace(".pdf", "")

    result = cloudinary.uploader.upload(
        local_pdf_path,
        public_id=f"facturacion/pdfs/{nombre_sin_ext}",
        resource_type="raw",
        overwrite=True,
        invalidate=True,
    )

    public_id = result.get("public_id", "")
    url = result.get("secure_url", "")

    return public_id, url


# ============================================================
# 2) DESCARGAR JSON DE FACTURAS
# ============================================================
def download_facturas_db(local_path: str = "facturas_db.json") -> Dict[str, Any]:
    try:
        # Obtenemos la URL del archivo
        result = cloudinary.api.resource(
            FACTURAS_DB_PUBLIC_ID,
            resource_type="raw",
        )
        url = result.get("secure_url")
        if not url:
            return {}

        # Agregamos timestamp para evitar caché
        url_sin_cache = f"{url}?t={int(time.time())}"

        r = httpx.get(url_sin_cache, timeout=15, follow_redirects=True)
        r.raise_for_status()

        # Cloudinary a veces devuelve el contenido vacío en caché
        content = r.text.strip()
        if not content:
            print("DEBUG → Cloudinary devolvió contenido vacío, retornando {}")
            return {}

        data = json.loads(content)

        # Guardar copia local
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return data

    except cloudinary.exceptions.NotFound:
        print("DEBUG → facturas_db.json no existe en Cloudinary todavía")
        return {}
    except json.JSONDecodeError as e:
        print(f"⚠️ Error parseando JSON desde Cloudinary: {e}")
        return {}
    except Exception as e:
        print(f"⚠️ Error descargando facturas_db desde Cloudinary: {e}")
        return {}


# ============================================================
# 3) SUBIR JSON DE FACTURAS
# ============================================================
def upload_facturas_db(local_path: str = "facturas_db.json") -> None:
    if not os.path.exists(local_path):
        print("DEBUG → No existe facturas_db.json local para subir")
        return

    try:
        result = cloudinary.uploader.upload(
            local_path,
            public_id=FACTURAS_DB_PUBLIC_ID,
            resource_type="raw",
            overwrite=True,
            invalidate=True,  # fuerza invalidar caché de Cloudinary
        )
        print("DEBUG → facturas_db.json subido a Cloudinary:", result.get("secure_url"))
    except Exception as e:
        print(f"⚠️ Error subiendo facturas_db a Cloudinary: {e}")
