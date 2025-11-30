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

# 🔥 IMPORTANTE — consultar registro de facturación
from json_db import esta_facturada

router = APIRouter(prefix="/api", tags=["ventas"])


# ============================================
# Función para limpiar el DNI (solo números)
# ============================================
def limpiar_dni(valor: str):
    if not valor:
        return None

    solo_numeros = "".join(c for c in valor if c.isdigit())
    return solo_numeros if solo_numeros else None


# ============================================
# LISTAR VENTAS ENTRE FECHAS
# ============================================
@router.get("/ventas")
async def listar_ventas(
    desde: date = Query(..., description="Fecha desde (YYYY-MM-DD)"),
    hasta: date = Query(..., description="Fecha hasta (YYYY-MM-DD)"),
):
    receipts_raw = await get_receipts_between(desde, hasta)

    if isinstance(receipts_raw, dict) and "error" in receipts_raw:
        return JSONResponse(status_code=400, content=receipts_raw)

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

    # 🔥 CORRECCIÓN CRÍTICA:
    # Marcar ventas facturadas según archivo JSON
    for v in ventas:
        v["already_invoiced"] = esta_facturada(v["receipt_id"])

    return ventas


# ============================================
# OBTENER DATOS DE UN CLIENTE (con DNI limpio)
# ============================================
@router.get("/clientes/{customer_id}")
async def obtener_cliente(customer_id: str):
    data = await get_customer(customer_id)

    if data is None:
        return {
            "exists": False,
            "id": customer_id,
            "name": None,
            "email": None,
            "phone": None,
            "dni": None,
        }

    dni_limpio = limpiar_dni(data.get("note"))

    return {
        "exists": True,
        "id": data.get("id"),
        "name": data.get("name"),
        "email": data.get("email"),
        "phone": data.get("phone_number"),
        "dni": dni_limpio,
    }


# ============================================
# DEBUG: Ver venta cruda
# ============================================
@router.get("/debug/venta/{receipt_id}")
async def debug_venta(receipt_id: str):
    from datetime import date, timedelta

    desde = date.today() - timedelta(days=365)
    hasta = date.today() + timedelta(days=1)

    receipts = await get_receipts_between(desde, hasta)

    for r in receipts:
        if r.get("receipt_number") == receipt_id:
            return r

    return {"error": "No se encontró ese recibo"}
