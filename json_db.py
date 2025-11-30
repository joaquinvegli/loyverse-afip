import json
import os
from typing import Dict, Any

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


def registrar_factura(receipt_id: str, datos: Dict[str, Any]):
    db = cargar_db()
    db[receipt_id] = datos
    guardar_db(db)
