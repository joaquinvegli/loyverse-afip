# loyverse_api.py
from datetime import date
from fastapi import APIRouter, Query

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
    ventas = [normalize_receipt(r) for r in receipts_raw]

    # Más adelante marcamos si ya fueron facturadas
    for v in ventas:
        v.setdefault("already_invoiced", False)

    return ventas
