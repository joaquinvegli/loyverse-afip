# facturar_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from afip import wsfe_facturar
from pdf_afip import generar_pdf_factura_c   # <--- IMPORT CORRECTO

router = APIRouter(prefix="/api", tags=["facturacion"])


# ====================================================
# Modelos de datos
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
# ENDPOINT PRINCIPAL — FACTURA C EN MODO SEGURO
# ====================================================
@router.post("/facturar")
async def facturar(req: FacturaRequest):

    # -------- MODO SEGURO PARA NO FACTURAR DE MÁS ------------
    if req.total > 100:
        raise HTTPException(
            status_code=400,
            detail="El total supera $100. Sistema en modo seguro de prueba."
        )

    try:
        tipo_comprobante = 11  # FACTURA C
        tipo_doc = 96          # DNI

        # fallback a consumidor final
        doc_nro = 0
        if req.cliente and req.cliente.dni:
            try:
                doc_nro = int(req.cliente.dni)
            except:
                doc_nro = 0

        # =====================================================
        # 1) Facturar en AFIP (CAE, vencimiento, nro comprobante)
        # =====================================================
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

        cae = result["cae"]
        venc = result["vencimiento"]
        cbte_nro = result["cbte_nro"]

        # =====================================================
        # 2) Generar PDF oficial AFIP
        # =====================================================
        pdf_b64 = generar_pdf_factura_c(
            cae=cae,
            vencimiento=venc,
            cbte_nro=cbte_nro,
            cliente_nombre=req.cliente.name,
            cliente_dni=req.cliente.dni,
            items=req.items,
            total=req.total,
        )

        # =====================================================
        # 3) Respuesta al frontend
        # =====================================================
        return {
            "status": "ok",
            "receipt_id": req.receipt_id,
            "cae": cae,
            "vencimiento": venc,
            "cbte_nro": cbte_nro,
            "pdf_base64": pdf_b64,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
