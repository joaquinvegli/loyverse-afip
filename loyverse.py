# loyverse.py
import httpx
import os
from datetime import date, datetime
from typing import List, Dict, Any

BASE_URL = "https://api.loyverse.com/v1.0"
TOKEN = os.environ.get("LOYVERSE_TOKEN")

if not TOKEN:
    raise Exception("LOYVERSE_TOKEN no está definida en Environment Variables")

HEADERS = {"Authorization": f"Bearer {TOKEN}"}


async def get_receipts_raw(params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Llama a /receipts de Loyverse y devuelve el JSON tal cual.
    Soporta params (para filtros, paginación, etc.)
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/receipts", headers=HEADERS, params=params)
        r.raise_for_status()
        return r.json()


async def get_receipt(receipt_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/receipts/{receipt_id}", headers=HEADERS)
        r.raise_for_status()
        return r.json()


async def get_receipts_between(desde: date, hasta: date) -> List[Dict[str, Any]]:
    """
    Obtiene los recibos (ventas) entre dos fechas usando created_at_min / max.
    Ajustamos al día completo (00:00 a 23:59).
    Maneja paginación con 'cursor' de Loyverse.
    """
    # Fechas en formato ISO con Z (UTC)
    created_at_min = f"{desde.isoformat()}T00:00:00Z"
    created_at_max = f"{hasta.isoformat()}T23:59:59Z"

    params = {
        "created_at_min": created_at_min,
        "created_at_max": created_at_max,
        "limit": 250,
    }

    all_receipts: List[Dict[str, Any]] = []
    cursor = None

    async with httpx.AsyncClient() as client:
        while True:
            if cursor:
                params["cursor"] = cursor

            r = await client.get(f"{BASE_URL}/receipts", headers=HEADERS, params=params)
            r.raise_for_status()
            data = r.json()

            receipts = data.get("receipts", [])
            all_receipts.extend(receipts)

            cursor = data.get("cursor")
            if not cursor:
                break

    return all_receipts


def normalize_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convierte un recibo de Loyverse al formato que va a usar el frontend.
    Si algún campo no existe en tu cuenta, no pasa nada, se usa valor por defecto.
    """
    # ID y fecha
    receipt_id = receipt.get("id") or receipt.get("receipt_number") or "SIN_ID"
    receipt_date = receipt.get("receipt_date") or receipt.get("created_at")

    # Total y moneda
    total_money = receipt.get("total_money") or {}
    total = float(total_money.get("amount", 0)) / 100 if isinstance(total_money.get("amount"), (int, float)) else 0.0
    currency = total_money.get("currency") or "ARS"

    # Método de pago (simplificado)
    payments = receipt.get("payments") or []
    payment_method = ", ".join(p.get("type", "Desconocido") for p in payments) if payments else "Desconocido"

    # Ítems de la venta
    items_raw = receipt.get("line_items") or []
    items = []
    for it in items_raw:
        name = it.get("item_name") or it.get("variant_name") or "Producto"
        qty = it.get("quantity", 1)
        # Precios suelen venir en centavos
        price_money = it.get("price", {})
        price = float(price_money.get("amount", 0)) / 100 if isinstance(price_money.get("amount"), (int, float)) else 0.0
        items.append(
            {
                "name": name,
                "quantity": qty,
                "price": price,
            }
        )

    # Cliente (si lo hay)
    customer_raw = receipt.get("customer") or {}
    customer = {
        "name": customer_raw.get("name"),
        "email": customer_raw.get("email"),
        # estos campos los completaremos cuando definamos bien cómo guardás los datos
        "tax_id": customer_raw.get("tax_id"),
        "doc_type": customer_raw.get("doc_type"),
        "doc_number": customer_raw.get("doc_number"),
    }

    return {
        "id": receipt_id,
        "date": receipt_date or datetime.utcnow().isoformat(),
        "total": total,
        "currency": currency,
        "payment_method": payment_method,
        "items": items,
        "customer": customer,
    }
