# email_api.py
import os
import base64
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from json_db import (
    obtener_factura,
    obtener_nota_credito,
)

router = APIRouter(prefix="/api", tags=["email"])


# ================================================
# MODELO REQUEST
# ================================================
class EmailRequest(BaseModel):
    receipt_id: str
    email: str


# ================================================
# ENVIAR EMAIL (BREVO) – FACTURA o NOTA DE CRÉDITO
# ================================================
@router.post("/enviar_email")
def api_enviar_email(req: EmailRequest):

    receipt_id = req.receipt_id
    email = req.email.strip()

    if not email:
        raise HTTPException(400, "Email inválido")

    # ------------------------------------------------
    # 1) Buscar comprobante (FACTURA o NOTA DE CRÉDITO)
    # ------------------------------------------------
    comprobante = obtener_factura(receipt_id)
    tipo = "FACTURA"

    if not comprobante:
        comprobante = obtener_nota_credito(receipt_id)
        tipo = "NOTA DE CREDITO"

    if not comprobante:
        raise HTTPException(
            404,
            f"No existe factura ni nota de crédito para receipt_id {receipt_id}"
        )

    drive_url = comprobante.get("drive_url")
    if not drive_url:
        raise HTTPException(
            400,
            "El comprobante no tiene URL de Google Drive"
        )

    # ------------------------------------------------
    # 2) Armar link directo a PDF (MISMO FIX DE ANTES)
    # ------------------------------------------------
    try:
        if "file/d/" in drive_url:
            file_id = drive_url.split("file/d/")[1].split("/")[0]
        elif "id=" in drive_url:
            file_id = drive_url.split("id=")[1].split("&")[0]
        else:
            raise Exception("Formato inesperado de URL de Drive")

        drive_direct_url = (
            f"https://drive.google.com/uc?id={file_id}&export=download"
        )
    except Exception as e:
        raise HTTPException(
            500,
            f"No se pudo procesar la URL de Drive ({drive_url}): {e}"
        )

    # ------------------------------------------------
    # 3) Descargar el PDF
    # ------------------------------------------------
    try:
        r = httpx.get(drive_direct_url, follow_redirects=True)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        raise HTTPException(
            500,
            f"No se pudo descargar el PDF desde Drive: {e}"
        )

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    # ------------------------------------------------
    # 4) Enviar email vía BREVO (IGUAL QUE ANTES)
    # ------------------------------------------------
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY")

    if not BREVO_API_KEY:
        raise HTTPException(500, "Falta BREVO_API_KEY en Render")

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY,
    }

    if tipo == "NOTA DE CREDITO":
        subject = "Nota de crédito - Top Fundas"
        html_content = """
            <p>Hola 👋</p>
            <p>Te enviamos la <strong>nota de crédito</strong> correspondiente a tu compra en <strong>Top Fundas</strong>.</p>
            <p>Ante cualquier duda, quedamos a disposición.</p>
            <p>Saludos ❤️</p>
        """
        filename = f"Nota_Credito_{comprobante.get('cbte_nro', receipt_id)}.pdf"
    else:
        subject = "Factura de compra - Top Fundas"
        html_content = """
            <p>Hola 👋</p>
            <p>Te enviamos la <strong>factura</strong> correspondiente a tu compra en <strong>Top Fundas</strong>.</p>
            <p>Muchas gracias por elegirnos ❤️</p>
        """
        filename = f"Factura_{comprobante.get('cbte_nro', receipt_id)}.pdf"

    payload = {
        "sender": {
            "name": "Top Fundas",
            "email": "topfundasbb@gmail.com"
        },
        "to": [
            {"email": email}
        ],
        "subject": subject,
        "htmlContent": html_content,
        "attachment": [
            {
                "content": pdf_b64,
                "name": filename
            }
        ]
    }

    try:
        response = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
    except Exception as e:
        raise HTTPException(
            500,
            f"Error enviando email con Brevo: {e}"
        )

    return {
        "status": "ok",
        "message": f"{tipo} enviada por email a {email}",
        "brevo_response": response.json(),
    }
