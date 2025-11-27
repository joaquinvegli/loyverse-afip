from fastapi import APIRouter, Query
from datetime import date

from loyverse import get_receipts_between

router = APIRouter(prefix="/debug", tags=["debug-loyverse"])

@router.get("/loyverse")
async def debug_loyverse_raw(
    desde: date = Query(...),
    hasta: date = Query(...)
):
    """
    Devuelve EXACTAMENTE lo que manda Loyverse, sin procesar.
    Para encontrar errores reales.
    """
    data = await get_receipts_between(desde, hasta)
    return {
        "raw_response": data
    }
