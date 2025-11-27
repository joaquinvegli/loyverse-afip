# loyverse.py
import httpx
import os
from datetime import datetime

BASE_URL = "https://api.loyverse.com/v1.0"
TOKEN = os.environ.get("LOYVERSE_TOKEN")

if not TOKEN:
    raise Exception("LOYVERSE_TOKEN no está definida en Environment Variables")


# ----------------------------------------------
# Obtener TODOS los recibos entre dos fechas
# ----------------------------------------------
async def get_receipts_between(desde, hasta):
    """
    Devuelve todos los recibos entre fechas usando Loyverse API.
    Maneja paginación, que es OBLIGATORIA.
    """
    headers = {"Authorization": f"Bearer {TOKEN}"}

    url = f"{BASE_URL}/receipts"
    params = {
        "limit": 250,
        "created_at_min": desde.isoformat(),
        "created_at_max": hasta.isoformat(),
    }

    all_receipts = []

    async with httpx.AsyncClient() as client:
        while True:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()

            all_receipts.extend(data.get("receipts", []))

            # paginación
            cursor = data.get("cursor")
            if not cursor:
                break
            params["cursor"] = cursor

    return all_receipts


# ----------------------------------------------
# Normalizar recibo para enviar al frontend
# ----------------------------------------------
def normalize_receipt(r):
    """
    Convierte el formato crudo de Loyverse a un formato simple.
    """
    return {
        "id": r.get("receipt_number"),
        "total": float(r.get("total_money", 0)),
        "datetime": r.get("created_at"),
        "customer": (r.get("customer", {}) or {}).get("name", ""),
        "items": [
            {
                "name": item.get("item_name"),
                "qty": item.get("quantity"),
                "price": float(item.get("price", 0)),
            }
            for item in r.get("line_items", [])
        ],
        "payment_method": (
            r.get("payments", [{}])[0].get("payment_type")
            if r.get("payments")
            else "Desconocido"
        ),
    }
