# facturar_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import base64
from datetime import datetime

from afip import wsfe_facturar
from pdf_afip import generar_pdf_factura_c

from json_db import esta_facturada, registrar_factura, obtener_factura
from google_drive_client import upload_pdf_to_drive  # Google Drive OAuth2

import traceback

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
    data = obtener_factura(receipt_id)
    if not data:
        return {"exists": False}
    return {"exists": True, "invoice": data}


@router.post("/facturar")
async def facturar(req: FacturaRequest):

    if esta_facturada(req.receipt_id):
        raise HTTPException(
            status_code=400,
            detail=f"La venta {req.receipt_id} ya fue facturada anteriormente."
        )

    if req.total > 100:
        raise HTTPException(
            status_code=400,
            detail="El total supera $100. Sistema en modo seguro."
        )

    try:
        tipo_comprobante = 11
        tipo_doc = 96

        # DNI numérico
        doc_nro = 0
        if req.cliente and req.cliente.dni:
            try:
                doc_nro = int(req.cliente.dni)
            except:
                doc_nro = 0

        # =====================================================
        # 1) LLAMADA A AFIP  (ahora con DEBUG REAL)
        # =====================================================
        try:
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
        except Exception as afip_error:
            print("🔥 ERROR CRÍTICO AFIP:")
            print("-------------------------------------------------")
            print(traceback.format_exc())
            print("-------------------------------------------------")
            raise HTTPException(
                status_code=500,
                detail="AFIP explotó antes de devolver CAE. Revisar logs."
            )

        print("DEBUG AFIP RESULT:", result)

        cae = result.get("cae")
        venc = result.get("vencimiento")
        cbte_nro = result.get("cbte_nro")
        pto_vta = result.get("pto_vta")

        if not cae:
            raise Exception("La AFIP no devolvió CAE. Error en la factura.")

        # =====================================================
        # 2) PDF local
        # =====================================================
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

        # =====================================================
        # 3) Google Drive
        # =====================================================
        pdf_filename = f"Factura_{cbte_nro}.pdf"
        drive_id, drive_url = upload_pdf_to_drive(pdf_path, pdf_filename)

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

        # =====================================================
        # 5) PDF base64
        # =====================================================
        with open(pdf_path, "rb") as f:
            pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

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
