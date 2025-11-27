# facturar_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from afip import wsfe_facturar   # función existente en tu afip.py

router = APIRouter(prefix="/api", tags=["facturacion"])


# ====================================================
# Esquema de datos recibidos desde el frontend
# ====================================================

class ClienteData(BaseModel):
    id: str | None = None
    name: str | None = None
    email: str | None = None
    dni: str | None = None


class ItemData(BaseModel):
    nombre: str
    cantidad: float
    precio_unitario: float


class FacturaRequest(BaseModel):
    receipt_id: str
    cliente: ClienteData
    items: list[ItemData]
    total: float


# ====================================================
# ENDPOINT PRINCIPAL — SIEMPRE FACTURA C
# ====================================================

@router.post("/facturar")
async def facturar(req: FacturaRequest):

    try:
        # -------------------------------------------------------
        # TIPO DE FACTURA Y DOCUMENTO PARA MONOTRIBUTISTA
        # -------------------------------------------------------

        tipo_comprobante = 11   # FACTURA C
        tipo_doc = 96           # DNI

        # Si tiene DNI (aunque no es obligatorio), lo usamos
        doc_nro = int(req.cliente.dni) if (req.cliente and req.cliente.dni) else 0

        # -------------------------------------------------------
        # 2) Llamar módulo AFIP (tu afip.py)
        # -------------------------------------------------------

        result = wsfe_facturar(
            tipo_cbte=tipo_comprobante,
            doc_tipo=tipo_doc,
            doc_nro=doc_nro,
            items=[{
                "descripcion": item.nombre,
                "cantidad": item.cantidad,
                "precio": item.precio_unitario
            } for item in req.items],
            total=req.total,
        )

        if "error" in result:
            raise Exception(result["error"])

        # -------------------------------------------------------
        # 3) Devolver CAE y datos
        # -------------------------------------------------------
        return {
            "status": "ok",
            "receipt_id": req.receipt_id,
            "cae": result.get("cae"),
            "vto_cae": result.get("vencimiento"),
            "pdf_url": None,   # Lo agregamos más adelante
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
