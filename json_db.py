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
        → se lee.
    - Si NO existe:
        → se descarga desde Google Drive.
          - Si tampoco está en Drive, se crea vacío {}.
    """
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            try:
                return download_facturas_db(DB_PATH)
            except Exception:
                return {}

    try:
        return download_facturas_db(DB_PATH)
    except Exception as e:
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
    Guarda localmente y luego sube a Google Drive.
    """
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

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


# ============================================================
# 🆕 NUEVO — LISTAR TODAS LAS FACTURAS
# ============================================================
def listado_facturas() -> Dict[str, Any]:
    """
    Devuelve el contenido completo del JSON de facturas.
    Si está vacío o no existe, devuelve {}.
    """
    return cargar_db()
