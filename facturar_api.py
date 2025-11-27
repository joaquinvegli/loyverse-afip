# facturar_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import base64
from afip import wsfe_facturar
from pdf_afip import generar_pdf_factura_c

# Datos fijos de tu negocio
RAZON_SOCIAL = "JOAQUIN VEGLI"
DOMICILIO = "ALSINA 155 LOC 15, BAHIA BLANCA, BUENOS AIRES. CP: 8000"
CUIT = "20391571865"

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
# ENDPOINT PRINCIPAL — FACTURA C EN MODO SEGURO
# ====================================================
@router.post("/facturar")
async def facturar(req: FacturaRequest):

    # -------- MODO SEGURO ------------
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
        # 1) Llamar AFIP — obtener CAE + fecha vencimiento
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

        # ================================
        # 2) Generar PDF oficial AFIP
        # ================================
        from datetime import datetime
        fecha_hoy = datetime.now().strftime("%d/%m/%Y")

        pdf_path = generar_pdf_factura_c(
            razon_social=RAZON_SOCIAL,
            domicilio=DOMICILIO,
            cuit=CUIT,
            pto_vta=int(result["pto_vta"]),
            cbte_nro=cbte_nro,
            fecha=fecha_hoy,
            cae=cae,
            cae_vto=venc,  # 🔥 CORRECTO: se llama cae_vto
            cliente_nombre=req.cliente.name,
            cliente_dni=req.cliente.dni,
            items=[{
                "descripcion": it.nombre,
                "cantidad": it.cantidad,
                "precio": it.precio_unitario,
            } for it in req.items],
            total=req.total,
        )

        # ================================
        # 3) Convertir PDF → base64
        # ================================
        with open(pdf_path, "rb") as f:
            pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

        # ================================
        # 4) Respuesta al frontend
        # ================================
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
