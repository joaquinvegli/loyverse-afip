# facturar_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import base64
from datetime import datetime

from afip import wsfe_facturar
from pdf_afip import generar_pdf_factura_c
from json_db import esta_facturada, guardar_factura, obtener_factura
from google_drive_client import upload_pdf_to_drive


# =========================
# Datos del emisor
# =========================
RAZON_SOCIAL = "JOAQUIN VEGLI"
DOMICILIO = "ALSINA 155 LOC 15, BAHIA BLANCA, BUENOS AIRES. CP: 8000"
CUIT = "20391571865"

router = APIRouter(prefix="/api", tags=["facturacion"])


# =========================
# MODELOS
# =========================
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
    cliente: Optional[ClienteData]
    items: List[ItemData]
    total: float


# =========================
# CONSULTAR FACTURA EXISTENTE
# =========================
@router.get("/factura/{receipt_id}")
def obtener_factura_existente(receipt_id: str):
    data = obtener_factura(receipt_id)
    if not data:
        return {"exists": False}

    return {
        "exists": True,
        "invoice": data,
    }


# =========================
# FACTURAR
# =========================
@router.post("/facturar")
async def facturar(req: FacturaRequest):

    # 1) Anti doble facturación
    if esta_facturada(req.receipt_id):
        raise HTTPException(
            status_code=400,
            detail=f"La venta {req.receipt_id} ya fue facturada anteriormente."
        )

    try:
        # Factura C
        TIPO_FACTURA_C = 11

        # 2) Llamada AFIP (FORMA CORRECTA)
        result = wsfe_facturar(
            tipo_cbte=TIPO_FACTURA_C,
            cliente={
                "dni": req.cliente.dni if req.cliente else None
            },
            items=[{
                "descripcion": it.nombre,
                "cantidad": it.cantidad,
                "precio": it.precio_unitario,
            } for it in req.items],
            total=req.total,
        )

        cae = result["cae"]
        venc = result["vencimiento"]
        cbte_nro = result["cbte_nro"]
        pto_vta = result["pto_vta"]

        # 3) PDF local
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
            cliente_nombre=req.cliente.name if req.cliente else "Consumidor Final",
            cliente_dni=req.cliente.dni if req.cliente else None,
            items=[{
                "descripcion": it.nombre,
                "cantidad": it.cantidad,
                "precio": it.precio_unitario,
            } for it in req.items],
            total=req.total,
        )

        # 4) Subir a Google Drive
        pdf_filename = f"Factura_{cbte_nro}.pdf"
        drive_id, drive_url = upload_pdf_to_drive(pdf_path, pdf_filename)

        # 5) Guardar factura en DB
        factura_data = {
            "cbte_nro": cbte_nro,
            "pto_vta": pto_vta,
            "cae": cae,
            "vencimiento": venc,
            "fecha": fecha_hoy,
            "drive_id": drive_id,
            "drive_url": drive_url,
        }
        guardar_factura(req.receipt_id, factura_data)

        # 6) PDF base64 para vista inmediata
        with open(pdf_path, "rb") as f:
            pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

        # 7) Respuesta
        return {
            "status": "ok",
            "receipt_id": req.receipt_id,
            "cae": cae,
            "vencimiento": venc,
            "cbte_nro": cbte_nro,
            "pdf_base64": pdf_b64,
            "invoice": factura_data,
            "pdf_url": drive_url,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
