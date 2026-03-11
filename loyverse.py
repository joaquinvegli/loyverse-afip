# loyverse.py
import httpx
import os
from datetime import datetime

BASE_URL = "https://api.loyverse.com/v1.0"
TOKEN = os.environ.get("LOYVERSE_TOKEN")
if not TOKEN:
    raise Exception("LOYVERSE_TOKEN no está definida en Environment Variables")


# ============================================
# OBTENER RECIBOS ENTRE FECHAS
# ============================================
async def get_receipts_between(desde, hasta):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    created_at_min = desde.strftime("%Y-%m-%dT00:00:00.000Z")
    created_at_max = hasta.strftime("%Y-%m-%dT23:59:59.999Z")

    url = (
        f"{BASE_URL}/receipts?"
        f"limit=250"
        f"&created_at_min={created_at_min}"
        f"&created_at_max={created_at_max}"
        f"&expand=customer"
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
# OBTENER DATOS DEL CLIENTE POR ID
# ============================================
async def get_customer(customer_id: str):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    url = f"{BASE_URL}/customers/{customer_id}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            return None
        return r.json()


# ============================================
# EXTRAER DNI DESDE CAMPOS CUSTOM DE LOYVERSE
# ============================================
def _extraer_dni(customer: dict) -> str | None:
    """
    Loyverse guarda datos extra del cliente en una lista llamada
    'customer_code' o en campos custom. Intentamos extraer el DNI
    de varios lugares posibles.
    """
    if not customer:
        return None

    # 1) Campo "note" — algunos negocios guardan el DNI ahí
    note = (customer.get("note") or "").strip()
    if note.isdigit() and 7 <= len(note) <= 11:
        return note

    # 2) Campo "customer_code"
    code = (customer.get("customer_code") or "").strip()
    if code.isdigit() and 7 <= len(code) <= 11:
        return code

    return None


# ============================================
# NORMALIZADOR DE RECIBOS
# ============================================
def normalize_receipt(r: dict) -> dict:
    # Cliente expandido (viene cuando se usa expand=customer)
    customer = r.get("customer") or {}
    cliente_id = r.get("customer_id")

    if customer and cliente_id:
        cliente_nombre = (
            f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
            or customer.get("name", "")
            or "Consumidor Final"
        )
        cliente_email = customer.get("email") or ""
        cliente_dni = _extraer_dni(customer)
    else:
        cliente_nombre = "Consumidor Final"
        cliente_email = ""
        cliente_dni = None

    return {
        "receipt_id": r.get("receipt_number"),
        "receipt_type": r.get("receipt_type"),
        "fecha": r.get("created_at"),
        "total": r.get("total_money"),
        "descuento_total": r.get("total_discount", 0),
        # cliente
        "cliente_id": cliente_id,
        "cliente_nombre": cliente_nombre,
        "cliente_email": cliente_email,
        "cliente_dni": cliente_dni,
        # items
        "items": [
            {
                "nombre": item.get("item_name"),
                "cantidad": item.get("quantity"),
                "precio_unitario": item.get("price"),
                "precio_total_item": item.get("total_money"),
            }
            for item in r.get("line_items", [])
        ],
        # pagos
        "pagos": [
            {
                "tipo": p.get("type"),
                "nombre": p.get("name"),
                "monto": p.get("money_amount"),
            }
            for p in r.get("payments", [])
        ],
    }
