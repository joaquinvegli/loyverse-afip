# facturar_api.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from afip import wsfe_facturar
from pdf_afip import generar_pdf_factura

router = APIRouter(prefix="/api", tags=["facturacion"])


# ====================================================
# Esquemas de datos
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
# ENDPOINT PRINCIPAL — FACTURAR + PDF
# ====================================================
@router.post("/facturar")
async def facturar(req: FacturaRequest):

    # MODO SEGURO DURANTE PRUEBAS
    if req.total > 100:
        raise HTTPException(
            status_code=400,
            detail="El total supera $100. Sistema en modo seguro de prueba."
        )

    try:
        tipo_comprobante = 11  # FACTURA C
        tipo_doc = 96          # DNI

        # consumidor final
        doc_nro = 0
        if req.cliente and req.cliente.dni:
            try:
                doc_nro = int(req.cliente.dni)
            except:
                doc_nro = 0

        # ================ FACTURAR EN AFIP ===================
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

        cbte_nro = result["cbte_nro"]
        cae = result["cae"]
        vencimiento = result["vencimiento"]

        # ================= GENERAR PDF ======================
        pdf_path = generar_pdf_factura(
            cbte_nro=cbte_nro,
            cae=cae,
            vto_cae=vencimiento,
            fecha_cbte=result.get("fecha", ""),
            cliente_nombre=req.cliente.name or "Consumidor Final",
            cliente_dni=req.cliente.dni or "",
            cliente_email=req.cliente.email or "",
            items=[{
                "nombre": i.nombre,
                "cantidad": i.cantidad,
                "precio_unitario": i.precio_unitario
            } for i in req.items],
            total=req.total,
        )

        pdf_url = f"/api/facturas/pdf/{cbte_nro}"

        return {
            "status": "ok",
            "receipt_id": req.receipt_id,
            "cae": cae,
            "vencimiento": vencimiento,
            "cbte_nro": cbte_nro,
            "pdf_url": pdf_url
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ====================================================
# ENDPOINT — DESCARGAR PDF POR CBTE_NRO
# ====================================================
@router.get("/facturas/pdf/{cbte_nro}")
async def descargar_pdf(cbte_nro: int):
    """
    Devuelve el PDF almacenado en /tmp generado previamente.
    """
    pdf_path = f"/tmp/FacturaC_{cbte_nro}.pdf"

    if not pdf_path or not pdf_path.endswith(".pdf"):
        raise HTTPException(status_code=404, detail="Archivo inválido")

    try:
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"FacturaC_{cbte_nro}.pdf"
        )
    except:
        raise HTTPException(status_code=404, detail="PDF no encontrado")
