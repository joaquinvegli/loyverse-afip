# facturar_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import base64
import os

from afip import wsfe_facturar
from pdf_afip import generar_pdf_factura_c

# JSON DB
from json_db import esta_facturada, registrar_factura, obtener_factura

RAZON_SOCIAL = "JOAQUIN VEGLI"
DOMICILIO = "ALSINA 155 LOC 15, BAHIA BLANCA, BUENOS AIRES. CP: 8000"
CUIT = "20391571865"

router = APIRouter(prefix="/api", tags=["facturacion"])


# ====================================================
# Esquemas
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
# Endpoint facturar
# ====================================================
@router.post("/facturar")
async def facturar(req: FacturaRequest):

    # 🔥 ANTI DOBLE FACTURACIÓN
    if esta_facturada(req.receipt_id):
        raise HTTPException(
            status_code=400,
            detail=f"La venta {req.receipt_id} ya fue facturada."
        )

    # 🚧 MODO SEGURO
    if req.total > 100:
        raise HTTPException(
            status_code=400,
            detail="El total supera $100. Sistema en modo seguro de prueba."
        )

    try:
        tipo_comprobante = 11  # Factura C
        tipo_doc = 96          # DNI

        doc_nro = 0
        if req.cliente and req.cliente.dni:
            try:
                doc_nro = int(req.cliente.dni)
            except:
                doc_nro = 0

        # 1) AFIP
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

        # 2) PDF
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

        # 🔥 3) Guardar copia permanente del PDF
        os.makedirs("facturas_pdf", exist_ok=True)
        destino = f"facturas_pdf/{req.receipt_id}.pdf"
        try:
            os.replace(pdf_path, destino)  # mueve el archivo
        except:
            # fallback copia
            with open(pdf_path, "rb") as fr:
                with open(destino, "wb") as fw:
                    fw.write(fr.read())

        # 4) Registrar en JSON
        registrar_factura(req.receipt_id, {
            "cbte_nro": cbte_nro,
            "pto_vta": pto_vta,
            "cae": cae,
            "vencimiento": venc,
            "fecha": fecha_hoy,
        })

        # 5) Devolver base64
        with open(destino, "rb") as f:
            pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

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


# ====================================================
# NUEVO: obtener PDF por receipt_id
# ====================================================
@router.get("/factura/pdf/{receipt_id}")
async def obtener_pdf(receipt_id: str):

    datos = obtener_factura(receipt_id)
    if not datos:
        raise HTTPException(
            status_code=404,
            detail="No hay factura registrada para este recibo."
        )

    pdf_path = f"facturas_pdf/{receipt_id}.pdf"
    if not os.path.exists(pdf_path):
        raise HTTPException(
            status_code=404,
            detail="El PDF no está guardado en el servidor."
        )

    with open(pdf_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return {
        "receipt_id": receipt_id,
        "pdf_base64": b64,
        "info": datos,
    }
