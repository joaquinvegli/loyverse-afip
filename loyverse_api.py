# loyverse_api.py
from datetime import date
from typing import List

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from loyverse import get_receipts_between, normalize_receipt

router = APIRouter(prefix="/api", tags=["ventas"])


@router.get("/ventas")
async def listar_ventas(
    desde: date = Query(..., description="Fecha desde (YYYY-MM-DD)"),
    hasta: date = Query(..., description="Fecha hasta (YYYY-MM-DD)"),
):
    """
    Devuelve ventas normalizadas desde Loyverse entre 'desde' y 'hasta'.
    """

    receipts_raw = await get_receipts_between(desde, hasta)

    # ← SI VIENE UN ERROR, DEVOLVER DIRECTAMENTE
    if isinstance(receipts_raw, dict) and "error" in receipts_raw:
        return JSONResponse(status_code=400, content=receipts_raw)

    # ← SI LOYVERSE NO DEVUELVE UNA LISTA, ERROR
    if not isinstance(receipts_raw, list):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Formato inesperado recibido desde Loyverse",
                "type": str(type(receipts_raw)),
                "data": receipts_raw
            }
        )

    # Normalizar ventas
    ventas = [normalize_receipt(r) for r in receipts_raw]

    # Agregar flag de facturado
    for v in ventas:
        v.setdefault("already_invoiced", False)

    return ventas
