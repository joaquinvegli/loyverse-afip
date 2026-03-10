# google_drive_client.py
import os
import json
import tempfile
from typing import Tuple, Dict, Any

import cloudinary
import cloudinary.uploader
import cloudinary.api

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
    """
    Sube un PDF a Cloudinary y devuelve (public_id, url).
    El nombre 'drive' en la función se mantiene para no romper
    el resto del código que ya la llama así.
    """
    # Quitamos la extensión del nombre para usar como public_id
    nombre_sin_ext = pdf_name.replace(".pdf", "")

    result = cloudinary.uploader.upload(
        local_pdf_path,
        public_id=f"facturacion/pdfs/{nombre_sin_ext}",
        resource_type="raw",   # PDF no es imagen, hay que usar raw
        overwrite=True,
    )

    public_id = result.get("public_id", "")
    url = result.get("secure_url", "")

    return public_id, url


# ============================================================
# 2) DESCARGAR JSON DE FACTURAS
# ============================================================
def download_facturas_db(local_path: str = "facturas_db.json") -> Dict[str, Any]:
    """
    Descarga el JSON de facturas desde Cloudinary.
    Si no existe, devuelve dict vacío.
    """
    try:
        result = cloudinary.api.resource(
            FACTURAS_DB_PUBLIC_ID,
            resource_type="raw",
        )
        url = result.get("secure_url")
        if not url:
            return {}

        import httpx
        r = httpx.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()

        # Guardar copia local
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return data

    except cloudinary.exceptions.NotFound:
        print("DEBUG → facturas_db.json no existe en Cloudinary todavía")
        return {}
    except Exception as e:
        print(f"⚠️ Error descargando facturas_db desde Cloudinary: {e}")
        return {}


# ============================================================
# 3) SUBIR JSON DE FACTURAS
# ============================================================
def upload_facturas_db(local_path: str = "facturas_db.json") -> None:
    """
    Sube el JSON de facturas a Cloudinary (sobreescribe si ya existe).
    """
    if not os.path.exists(local_path):
        print("DEBUG → No existe facturas_db.json local para subir")
        return

    try:
        result = cloudinary.uploader.upload(
            local_path,
            public_id=FACTURAS_DB_PUBLIC_ID,
            resource_type="raw",
            overwrite=True,
        )
        print("DEBUG → facturas_db.json subido a Cloudinary:", result.get("secure_url"))
    except Exception as e:
        print(f"⚠️ Error subiendo facturas_db a Cloudinary: {e}")
