# email_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from json_db import obtener_factura
from drive_utils import obtener_pdf_drive  # asumimos que ESTE sí existe (ya lo usabas)
from email_sender import enviar_email_con_adjunto  # ESTE es el que ya usabas antes

router = APIRouter(prefix="/api", tags=["email"])


# ============================
# MODELO REQUEST
# ============================
class EnviarEmailRequest(BaseModel):
    receipt_id: str
    email: str


# ============================
# ENDPOINT ENVIAR FACTURA / NC
# ============================
@router.post("/enviar_email")
def enviar_email(req: EnviarEmailRequest):
    receipt_id = req.receipt_id
    email = req.email.strip()

    if not email:
        raise HTTPException(status_code=400, detail="Email inválido")

    # 1) Buscar comprobante en JSON (factura o NC)
    factura = obtener_factura(receipt_id)
    if not factura:
        raise HTTPException(
            status_code=404,
            detail="No se encontró el comprobante para enviar por mail",
        )

    # 2) Obtener PDF desde Google Drive
    pdf_bytes = obtener_pdf_drive(factura)
    if not pdf_bytes:
        raise HTTPException(
            status_code=500,
            detail="No se pudo obtener el PDF desde Google Drive",
        )

    # 3) Armar asunto y cuerpo (factura o nota de crédito)
    tipo = factura.get("tipo", "FACTURA").upper()

    if tipo == "NC":
        asunto = "Nota de crédito"
        cuerpo = (
            "Hola,\n\n"
            "Te enviamos la nota de crédito correspondiente a tu compra.\n\n"
            "Ante cualquier duda, quedamos a disposición.\n\n"
            "Saludos."
        )
    else:
        asunto = "Factura"
        cuerpo = (
            "Hola,\n\n"
            "Te enviamos la factura correspondiente a tu compra.\n\n"
            "Gracias por tu preferencia.\n\n"
            "Saludos."
        )

    # 4) Enviar email (FUNCIÓN QUE YA EXISTÍA ANTES)
    try:
        enviar_email_con_adjunto(
            to=email,
            subject=asunto,
            body=cuerpo,
            pdf_bytes=pdf_bytes,
            filename=f"{tipo}_{factura.get('cbte_nro', receipt_id)}.pdf",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error enviando email: {str(e)}",
        )

    return {"ok": True}
