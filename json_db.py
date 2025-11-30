import json
import os
from typing import Dict, Any
from datetime import datetime

DB_PATH = "facturas_db.json"


def cargar_db() -> Dict[str, Any]:
    if not os.path.exists(DB_PATH):
        return {}
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def guardar_db(data: Dict[str, Any]):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def esta_facturada(receipt_id: str) -> bool:
    db = cargar_db()
    return receipt_id in db


def obtener_factura(receipt_id: str) -> Dict[str, Any] | None:
    """
    Devuelve todos los datos guardados de la factura:
    cbte_nro, pto_vta, cae, vencimiento, fecha.
    """
    db = cargar_db()
    return db.get(receipt_id)


def registrar_factura(receipt_id: str, datos: Dict[str, Any]):
    """
    Guarda los datos de la factura y agrega automáticamente la fecha
    (YYYY-MM-DD) si no estaba incluida.
    """
    db = cargar_db()

    # Agregar fecha si no existe
    if "fecha" not in datos:
        datos["fecha"] = datetime.now().strftime("%Y-%m-%d")

    db[receipt_id] = datos
    guardar_db(db)
