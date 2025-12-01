import json
import os
from typing import Dict, Any

from google_drive_client import download_facturas_db, upload_facturas_db

DB_PATH = "facturas_db.json"


def cargar_db() -> Dict[str, Any]:
    """
    Carga la base de datos de facturas.

    Lógica:
    - Si existe facturas_db.json local:
        → se intenta leer.
    - Si NO existe:
        → se descarga desde Google Drive (download_facturas_db).
          - Si tampoco existe en Drive, se crea vacío {} tanto en Drive como local.
    """
    # Si el archivo existe localmente, intentamos leerlo.
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # Si está corrupto, intentamos bajar desde Drive como fuente de verdad
            try:
                return download_facturas_db(DB_PATH)
            except Exception:
                # Si incluso eso falla, devolvemos base vacía
                return {}

    # Si no existe local, intentamos descargar desde Drive
    try:
        return download_facturas_db(DB_PATH)
    except Exception as e:
        # Si falla la descarga, como último recurso devolvemos {}
        # y tratamos de crear un archivo local vacío.
        print("⚠️ Error descargando facturas_db.json desde Drive:", e)
        data: Dict[str, Any] = {}
        try:
            with open(DB_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return data


def guardar_db(data: Dict[str, Any]):
    """
    Guarda la base de datos de facturas localmente
    y la sube a Google Drive.

    Si la subida a Drive falla, NO rompe la facturación:
    solo se loguea el error.
    """
    # Guardar local
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Subir a Drive (best effort)
    try:
        upload_facturas_db(DB_PATH)
    except Exception as e:
        print("⚠️ Error subiendo facturas_db.json a Drive:", e)


def esta_facturada(receipt_id: str) -> bool:
    db = cargar_db()
    return receipt_id in db


def registrar_factura(receipt_id: str, datos: Dict[str, Any]):
    db = cargar_db()
    db[receipt_id] = datos
    guardar_db(db)


def obtener_factura(receipt_id: str) -> Dict[str, Any] | None:
    db = cargar_db()
    return db.get(receipt_id)
