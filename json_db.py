import os
import json
from typing import Any, Dict, Optional

from google_drive_client import download_facturas_db, upload_facturas_db

LOCAL_PATH = "facturas_db.json"


def _load_db() -> Dict[str, Any]:
    """
    DB en Drive. Estructura:
    {
      "facturas": { "<sale_receipt_id>": {...invoice...} },
      "notas_credito": { "<refund_receipt_id>": {...nc...} }
    }
    Si venías guardando solo un dict plano, lo convertimos sin romper.
    """
    data = download_facturas_db(LOCAL_PATH) or {}

    # Compat: si antes era dict plano de facturas
    if "facturas" not in data and "notas_credito" not in data:
        return {"facturas": data, "notas_credito": {}}

    if "facturas" not in data:
        data["facturas"] = {}
    if "notas_credito" not in data:
        data["notas_credito"] = {}

    return data


def _save_db(db: Dict[str, Any]) -> None:
    with open(LOCAL_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    upload_facturas_db(LOCAL_PATH)


# -------------------------
# FACTURAS (VENTAS)
# -------------------------
def obtener_factura(receipt_id: str) -> Optional[Dict[str, Any]]:
    db = _load_db()
    return db.get("facturas", {}).get(receipt_id)


def esta_facturada(receipt_id: str) -> bool:
    return obtener_factura(receipt_id) is not None


def guardar_factura(receipt_id: str, info: Dict[str, Any]) -> None:
    db = _load_db()
    db["facturas"][receipt_id] = info
    _save_db(db)


# -------------------------
# NOTAS DE CRÉDITO (REEMBOLSOS)
# -------------------------
def obtener_nota_credito(refund_receipt_id: str) -> Optional[Dict[str, Any]]:
    db = _load_db()
    return db.get("notas_credito", {}).get(refund_receipt_id)


def nota_credito_emitida(refund_receipt_id: str) -> bool:
    return obtener_nota_credito(refund_receipt_id) is not None


def guardar_nota_credito(refund_receipt_id: str, info: Dict[str, Any]) -> None:
    db = _load_db()
    db["notas_credito"][refund_receipt_id] = info
    _save_db(db)
