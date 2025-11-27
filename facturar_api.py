# facturar_api.py
import os
import base64
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from afip import wsfe_facturar
from pdf_afip import generar_pdf_factura_c

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

        # ---------------------------
        # 1) Llamar AFIP (WSFE)
        # ---------------------------
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

        cae = result.get("cae")
        vto = result.get("vencimiento")
        cbte_nro = result.get("cbte_nro")

        # ---------------------------
        # 2) Generar PDF con QR AFIP
        # ---------------------------
        cuit_emisor = os.environ.get("AFIP_CUIT", "")
        pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

        # Fecha del comprobante en formato AAAAMMDD
        fecha_cbte = datetime.now().strftime("%Y%m%d")

        # Datos fijos del emisor (tus datos)
        razon_social = "JOAQUIN VEGLI"
        domicilio = "ALSINA 155 LOC 15, BAHIA BLANCA, BUENOS AIRES. CP: 8000"

        # Armar items para el PDF (incluyendo importe por línea)
        items_pdf = []
        for it in req.items:
            importe_item = float(it.cantidad) * float(it.precio_unitario)
            items_pdf.append({
                "descripcion": it.nombre,
                "cantidad": it.cantidad,
                "precio_unitario": it.precio_unitario,
                "importe": importe_item,
            })

        datos_pdf = {
            "razon_social": razon_social,
            "domicilio": domicilio,
            "cuit_emisor": cuit_emisor,
            "pto_vta": pto_vta,
            "tipo_cbte": tipo_comprobante,
            "cbte_nro": cbte_nro,
            "fecha_cbte": fecha_cbte,
            "cliente_nombre": req.cliente.name or "Consumidor Final",
            "cliente_doc_tipo": tipo_doc if doc_nro else 99,
            "cliente_doc_nro": doc_nro,
            "items": items_pdf,
            "total": req.total,
            "cae": cae,
            "vto_cae": vto,
        }

        pdf_bytes = generar_pdf_factura_c(datos_pdf)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        # ---------------------------
        # 3) Respuesta al frontend
        # ---------------------------
        vto_final = (
            result.get("vencimiento")
            or result.get("CAEFchVto")
            or result.get("vto_cae")
            or None
        )

        return {
            "status": "ok",
            "receipt_id": req.receipt_id,
            "cae": cae,
            "vencimiento": vto_final,
            "cbte_nro": cbte_nro,
            "pdf_base64": pdf_b64,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
