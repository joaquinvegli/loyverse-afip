# loyverse.py
import httpx
import os
from datetime import datetime

BASE_URL = "https://api.loyverse.com/v1.0"
TOKEN = os.environ.get("LOYVERSE_TOKEN")
if not TOKEN:
    raise Exception("LOYVERSE_TOKEN no está definida en Environment Variables")


async def get_receipts_between(desde, hasta):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    created_at_min = desde.strftime("%Y-%m-%dT00:00:00.000Z")
    created_at_max = hasta.strftime("%Y-%m-%dT23:59:59.999Z")

    all_receipts = []
    cursor = None

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            url = (
                f"{BASE_URL}/receipts?"
                f"limit=250"
                f"&created_at_min={created_at_min}"
                f"&created_at_max={created_at_max}"
                f"&expand=customer"
            )
            if cursor:
                url += f"&cursor={cursor}"

            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                return {
                    "error": "Loyverse devolvió error",
                    "status": r.status_code,
                    "body": r.text,
                    "url": url,
                }

            data = r.json()
            receipts = data.get("receipts", [])
            all_receipts.extend(receipts)

            cursor = data.get("cursor")
            if not cursor or len(receipts) < 250:
                break

    return all_receipts


async def get_customer(customer_id: str):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    url = f"{BASE_URL}/customers/{customer_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=headers)
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            return None
        return r.json()


def _clasificar_documento(customer: dict) -> tuple:
    if not customer:
        return None, None
    candidatos = [
        (customer.get("note") or "").strip(),
        (customer.get("customer_code") or "").strip(),
    ]
    for raw in candidatos:
        if not raw:
            continue
        solo_digitos = "".join(c for c in raw if c.isdigit())
        if not solo_digitos:
            continue
        if len(solo_digitos) == 11:
            return "cuit", solo_digitos
        if 7 <= len(solo_digitos) <= 8:
            return "dni", solo_digitos
    return None, None


def _armar_domicilio(customer: dict) -> str | None:
    if not customer:
        return None
    partes = []
    address = (customer.get("address") or "").strip()
    city = (customer.get("city") or "").strip()
    postal_code = (customer.get("postal_code") or "").strip()
    if address:
        partes.append(address)
    if city:
        partes.append(city)
    if postal_code:
        partes.append(f"CP: {postal_code}")
    return ", ".join(partes) if partes else None


def normalize_receipt(r: dict) -> dict:
    customer = r.get("customer") or {}
    cliente_id = r.get("customer_id")

    if customer and cliente_id:
        cliente_nombre = (
            f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
            or customer.get("name", "")
            or "Consumidor Final"
        )
        cliente_email = customer.get("email") or ""
        doc_tipo, doc_nro = _clasificar_documento(customer)
        cliente_dni = doc_nro if doc_tipo == "dni" else None
        cliente_cuit = doc_nro if doc_tipo == "cuit" else None
        cliente_domicilio = _armar_domicilio(customer)
    else:
        cliente_nombre = "Consumidor Final"
        cliente_email = ""
        cliente_dni = None
        cliente_cuit = None
        cliente_domicilio = None

    return {
        "receipt_id": r.get("receipt_number"),
        "receipt_type": r.get("receipt_type"),
        "fecha": r.get("created_at"),
        "total": r.get("total_money"),
        "descuento_total": r.get("total_discount", 0),
        "cliente_id": cliente_id,
        "cliente_nombre": cliente_nombre,
        "cliente_email": cliente_email,
        "cliente_dni": cliente_dni,
        "cliente_cuit": cliente_cuit,
        "cliente_domicilio": cliente_domicilio,
        "items": [
            {
                "nombre": item.get("item_name"),
                "cantidad": item.get("quantity"),
                "precio_unitario": item.get("price"),
                "precio_total_item": item.get("total_money"),
            }
            for item in r.get("line_items", [])
        ],
        "pagos": [
            {
                "tipo": p.get("type"),
                "nombre": p.get("name"),
                "monto": p.get("money_amount"),
            }
            for p in r.get("payments", [])
        ],
    }
