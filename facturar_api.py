# facturar_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import base64
from datetime import datetime

from afip import wsfe_facturar
from pdf_afip import generar_pdf_factura_c

from json_db import esta_facturada, registrar_factura, obtener_factura
from google_drive_client import upload_pdf_to_drive  # 👈 OAuth2 Google Drive


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


@router.get("/factura/{receipt_id}")
def obtener_factura_existente(receipt_id: str):
    """
    Permite al frontend consultar si ya existe una factura emitida
    y obtener sus datos (incluyendo drive_url).
    """
    data = obtener_factura(receipt_id)
    if not data:
        return {"exists": False}

    return {
        "exists": True,
        "invoice": data,
    }


@router.post("/facturar")
async def facturar(req: FacturaRequest):

    # 0) Anti doble facturación REAL
    if esta_facturada(req.receipt_id):
        factura = obtener_factura(req.receipt_id)
        raise HTTPException(
            status_code=400,
            detail=f"La venta {req.receipt_id} ya fue facturada anteriormente."
        )

    # 🔥 ELIMINADO: límite de $100
    # Ya no existe el modo seguro

    try:
        tipo_comprobante = 11  # FACTURA C

        # =====================================================
        # 1) Determinar tipo y número de documento
        # =====================================================
        doc_nro = 0
        tipo_doc = 99  # default: Consumidor Final

        if req.cliente and req.cliente.dni:
            try:
                posible_dni = int(req.cliente.dni)
                if posible_dni > 0:
                    tipo_doc = 96  # DNI
                    doc_nro = posible_dni
            except:
                tipo_doc = 99
                doc_nro = 0

        # 2) AFIP — CAE + vencimiento
        result = wsfe_facturar(
            tipo_cbte=tipo_comprobante,
            doc_tipo=tipo_doc,
            doc_nro=doc_nro,
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
            cliente_nombre=req.cliente.name,
            cliente_dni=req.cliente.dni,
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

        # 5) Guardar factura
        factura_data = {
            "cbte_nro": cbte_nro,
            "pto_vta": pto_vta,
            "cae": cae,
            "vencimiento": venc,
            "fecha": fecha_hoy,
            "drive_id": drive_id,
            "drive_url": drive_url,
        }
        registrar_factura(req.receipt_id, factura_data)

        # 6) PDF en base64 para vista rápida
        with open(pdf_path, "rb") as f:
            pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

        # 7) Respuesta final
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
