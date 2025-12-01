# facturar_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import base64
import os

from afip import wsfe_facturar
from pdf_afip import generar_pdf_factura_c

from json_db import esta_facturada, registrar_factura
from google_drive_client import upload_pdf_to_drive  # 👈 (ESTA VERSIÓN YA TENÍA DRIVE)

RAZON_SOCIAL = "JOAQUIN VEGLI"
DOMICILIO = "ALSINA 155 LOC 15, BAHIA BLANCA, BUENOS AIRES. CP: 8000"
CUIT = "20391571865"

router = APIRouter(prefix="/api", tags=["facturacion"])


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


@router.post("/facturar")
async def facturar(req: FacturaRequest):

    # -------- ANTI DOBLE FACTURACIÓN -----------------
    if esta_facturada(req.receipt_id):
        raise HTTPException(
            status_code=400,
            detail=f"La venta {req.receipt_id} ya fue facturada anteriormente."
        )

    # -------- MODO SEGURO ------------ (esto ya existía)
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
        pto_vta = result["pto_vta"]

        # ================================
        # 2) Generar PDF oficial AFIP
        # ================================
        from datetime import datetime
        fecha_hoy = datetime.now().strftime("%d/%m/%Y")

        pdf_path = generar_pdf_factura_c(
            razon_social=RAZON_SOCIAL,
            domicilio=DOMICILIO,
            cuit=CUIT,
            pto_vta=int(pto_vta),
            cbte_nro=cbte_nro,
            fecha=fecha_hoy,
            cae=cae,
            cae_vto=venc,
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
        # 3) Subir PDF a Google Drive
        # ================================
        drive_id, drive_url = upload_pdf_to_drive(pdf_path, req.receipt_id)

        # ================================
        # 4) REGISTRAR FACTURA
        # ================================
        registrar_factura(req.receipt_id, {
            "cbte_nro": cbte_nro,
            "pto_vta": pto_vta,
            "cae": cae,
            "vencimiento": venc,
            "fecha": fecha_hoy,
            "drive_id": drive_id,
            "drive_url": drive_url,
        })

        # ================================
        # 5) Leer PDF local → base64
        # ================================
        with open(pdf_path, "rb") as f:
            pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

        # ================================
        # 6) Respuesta al frontend
        # ================================
        return {
            "status": "ok",
            "receipt_id": req.receipt_id,
            "cae": cae,
            "vencimiento": venc,
            "cbte_nro": cbte_nro,
            "pdf_base64": pdf_b64,
            "pdf_url": drive_url,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
