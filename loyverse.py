# loyverse.py
import httpx
import os
from datetime import datetime

BASE_URL = "https://api.loyverse.com/v1.0"
TOKEN = os.environ.get("LOYVERSE_TOKEN")

if not TOKEN:
    raise Exception("LOYVERSE_TOKEN no está definida en Environment Variables")


# ============================================
# RAW REQUEST ENTRE FECHAS (funciona perfecto)
# ============================================
async def get_receipts_between(desde, hasta):
    headers = {"Authorization": f"Bearer {TOKEN}"}

    created_at_min = desde.strftime("%Y-%m-%dT00:00:00.000Z")
    created_at_max = hasta.strftime("%Y-%m-%dT23:59:59.999Z")

    url = (
        f"{BASE_URL}/receipts?"
        f"limit=250&created_at_min={created_at_min}&created_at_max={created_at_max}"
    )

    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            return {
                "error": "Loyverse devolvió error",
                "status": r.status_code,
                "body": r.text,
                "url": url,
            }
        return r.json().get("receipts", [])


# ============================================
# NORMALIZADOR (Aquí estaba el problema)
# ============================================
def normalize_receipt(r: dict) -> dict:
    """
    Convierte una venta de Loyverse al formato que necesita tu web app.
    """

    return {
        "receipt_id": r.get("receipt_number"),
        "receipt_type": r.get("receipt_type"),
        "fecha": r.get("created_at"),
        "total": r.get("total_money"),
        "descuento_total": r.get("total_discount", 0),

        # Cliente (si existe)
        "cliente_id": r.get("customer_id"),

        # Items
        "items": [
            {
                "nombre": item.get("item_name"),
                "cantidad": item.get("quantity"),
                "precio_unitario": item.get("price"),
                "precio_total_item": item.get("total_money"),
            }
            for item in r.get("line_items", [])
        ],

        # Método de pago
        "pagos": [
            {
                "tipo": p.get("type"),
                "nombre": p.get("name"),
                "monto": p.get("money_amount"),
            }
            for p in r.get("payments", [])
        ],

        # Marcador para saber si ya está facturada
        "already_invoiced": False,
    }
