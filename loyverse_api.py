# loyverse_api.py
from datetime import date
from typing import List

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from loyverse import (
    get_receipts_between,
    normalize_receipt,
    get_customer,
)

router = APIRouter(prefix="/api", tags=["ventas"])


# ============================================
# LISTAR VENTAS ENTRE FECHAS
# ============================================
@router.get("/ventas")
async def listar_ventas(
    desde: date = Query(..., description="Fecha desde (YYYY-MM-DD)"),
    hasta: date = Query(..., description="Fecha hasta (YYYY-MM-DD)"),
):
    """
    Devuelve ventas normalizadas desde Loyverse entre 'desde' y 'hasta'.
    """

    receipts_raw = await get_receipts_between(desde, hasta)

    # Si Loyverse devolvió error -> pasar el error directo
    if isinstance(receipts_raw, dict) and "error" in receipts_raw:
        return JSONResponse(status_code=400, content=receipts_raw)

    # Si vino algo raro
    if not isinstance(receipts_raw, list):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Formato inesperado recibido desde Loyverse",
                "type": str(type(receipts_raw)),
                "data": receipts_raw,
            },
        )

    # Normalizar ventas
    ventas = [normalize_receipt(r) for r in receipts_raw]

    # Agregar flag factura
    for v in ventas:
        v.setdefault("already_invoiced", False)

    return ventas


# ============================================
# NUEVO: OBTENER DATOS DE UN CLIENTE (FIXED)
# ============================================
@router.get("/clientes/{customer_id}")
async def obtener_cliente(customer_id: str):
    """
    Devuelve datos del cliente desde Loyverse.
    Si no existe → exists = False.
    """

    data = await get_customer(customer_id)

    # Si no existe
    if data is None:
        return {
            "exists": False,
            "id": customer_id,
            "name": None,
            "email": None,
            "phone": None,
        }

    # En TU cuenta Loyverse, la respuesta es directa:
    # {
    #   "id": "...",
    #   "name": "...",
    #   "email": "...",
    #   "phone_number": "..."
    # }

    return {
        "exists": True,
        "id": data.get("id"),
        "name": data.get("name"),
        "email": data.get("email"),
        "phone": data.get("phone_number"),
    }


# ============================================
# DEBUG: Ver venta cruda
# ============================================
@router.get("/debug/venta/{receipt_id}")
async def debug_venta(receipt_id: str):
    """
    Devuelve la venta RAW exacta antes de normalizar.
    Sirve para ver cómo Loyverse envía el cliente.
    """
    from datetime import date, timedelta

    desde = date.today() - timedelta(days=365)
    hasta = date.today() + timedelta(days=1)

    receipts = await get_receipts_between(desde, hasta)

    for r in receipts:
        if r.get("receipt_number") == receipt_id:
            return r

    return {"error": "No se encontró ese recibo"}
