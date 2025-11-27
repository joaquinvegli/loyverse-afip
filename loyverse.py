import httpx
import os
from datetime import datetime, timedelta

BASE_URL = "https://api.loyverse.com/v1.0"
TOKEN = os.environ.get("LOYVERSE_TOKEN")

if not TOKEN:
    raise Exception("LOYVERSE_TOKEN no está definida en Environment Variables")


async def get_receipts_between(desde, hasta):
    """
    Pide recibos entre fechas en formato ISO con hora.
    Loyverse requiere fecha + hora, si no devuelve 400 Bad Request.
    """
    # Convertimos date → string con hora incluida
    desde_str = f"{desde}T00:00:00"
    hasta_str = f"{hasta}T23:59:59"

    headers = {"Authorization": f"Bearer {TOKEN}"}

    receipts = []
    cursor = None

    async with httpx.AsyncClient() as client:
        while True:
            params = {
                "limit": 250,
                "created_at_min": desde_str,
                "created_at_max": hasta_str,
            }
            if cursor:
                params["cursor"] = cursor

            r = await client.get(f"{BASE_URL}/receipts", headers=headers, params=params)

            # Si falla, que diga el motivo exacto:
            try:
                r.raise_for_status()
            except Exception:
                return {
                    "error": "Loyverse devolvió error",
                    "status": r.status_code,
                    "body": r.text,
                    "url": str(r.url)
                }

            data = r.json()

            receipts.extend(data.get("receipts", []))
            cursor = data.get("cursor")

            if not cursor:
                break

    return receipts


def normalize_receipt(r):
    """
    Normaliza la estructura del recibo de Loyverse.
    """
    return {
        "receipt_id": r.get("receipt_id"),
        "date": r.get("created_at"),
        "total": float(r.get("total_money", 0)),
        "items": [
            {
                "name": i.get("item_name"),
                "price": float(i.get("price")),
                "qty": float(i.get("quantity")),
            }
            for i in r.get("line_items", [])
        ],
        "payments": [
            {
                "method": p.get("payment_type"),
                "amount": float(p.get("amount", 0)),
            }
            for p in r.get("payments", [])
        ],
        "customer": r.get("customer", {}),
    }
