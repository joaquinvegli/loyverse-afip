import httpx
import os
from datetime import date, datetime, time

BASE_URL = "https://api.loyverse.com/v1.0"
TOKEN = os.environ.get("LOYVERSE_TOKEN")

if not TOKEN:
    raise Exception("LOYVERSE_TOKEN no está definida en Environment Variables")


async def get_receipts_between(desde: date, hasta: date):
    """
    Obtiene recibos entre dos fechas usando los formatos correctos requeridos por Loyverse.
    Formato obligatorio: YYYY-MM-DDTHH:mm:ss.sssZ
    """

    headers = {"Authorization": f"Bearer {TOKEN}"}

    # Formatos correctos
    min_dt = datetime.combine(desde, time(0, 0, 0)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    max_dt = datetime.combine(hasta, time(23, 59, 59)).strftime("%Y-%m-%dT%H:%M:%S.999Z")

    url = (
        f"{BASE_URL}/receipts"
        f"?limit=250"
        f"&created_at_min={min_dt}"
        f"&created_at_max={max_dt}"
    )

    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)

        try:
            r.raise_for_status()
        except Exception:
            return {
                "error": "Loyverse devolvió error",
                "status": r.status_code,
                "body": r.text,
                "url": str(r.url),
            }

        data = r.json()

        # Loyverse devuelve {"receipts": [...]}
        if "receipts" in data:
            return data["receipts"]

        return {
            "error": "Formato inesperado",
            "raw": data,
            "url": str(r.url)
        }


def normalize_receipt(r: dict):
    """
    Normaliza recibos de Loyverse
    """
    return {
        "receipt_id": r.get("receipt_id"),
        "number": r.get("receipt_number"),
        "total": r.get("total_money"),
        "created_at": r.get("created_at"),
        "items": [
            {
                "name": i["item_name"],
                "qty": i["quantity"],
                "price": i["price"]
            }
            for i in r.get("line_items", [])
        ],
        "payments": [
            {
                "type": p["payment_type"],
                "amount": p["amount"]
            }
            for p in r.get("payments", [])
        ]
    }
