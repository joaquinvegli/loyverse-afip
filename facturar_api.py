# facturar_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from afip import wsfe_facturar  # ahora sí existe en afip.py

router = APIRouter(prefix="/api", tags=["facturacion"])


# ====================================================
# Esquema de datos recibidos desde el frontend
# ====================================================

class ClienteData(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    dni: Optional[str] = None


class ItemData(BaseModel):
    nombre: str
    cantidad: float
    precio_unitario: float


class FacturaRequest(BaseModel):
    receipt_id: str
    cliente: ClienteData
    items: List[ItemData]
    total: float


# ====================================================
# ENDPOINT PRINCIPAL — SIEMPRE FACTURA C
# ====================================================

@router.post("/facturar")
async def facturar(req: FacturaRequest):

    # -------------------------------------------------------
    # MODO SEGURO: EVITAR FACTURAS GRANDES EN PRODUCCIÓN
    # -------------------------------------------------------
    if req.total > 100:
        raise HTTPException(
            status_code=400,
            detail="El total supera $100. Sistema en modo seguro de prueba. Ajusta el límite en facturar_api.py para facturas reales."
        )

    try:
        # Siempre FACTURA C (monotributista)
        tipo_comprobante = 11   # FACTURA C
        tipo_doc = 96           # DNI

        # Si tiene DNI, lo usamos; si no, consumidor final
        doc_nro = 0
        if req.cliente and req.cliente.dni:
            try:
                doc_nro = int(req.cliente.dni)
            except ValueError:
                doc_nro = 0

        # Llamar AFIP
        result = wsfe_facturar(
            tipo_cbte=tipo_comprobante,
            doc_tipo=tipo_doc,
            doc_nro=doc_nro,
            items=[{
                "descripcion": item.nombre,
                "cantidad": item.cantidad,
                "precio": item.precio_unitario,
            } for item in req.items],
            total=req.total,
        )

        return {
            "status": "ok",
            "receipt_id": req.receipt_id,
            "cae": result.get("cae"),
            "vto_cae": result.get("vencimiento"),
            "cbte_nro": result.get("cbte_nro"),
            "pdf_url": None,  # lo agregamos después cuando generemos PDF
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
