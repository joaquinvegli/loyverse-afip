# email_api.py (BREVO API)
import os
import base64
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from json_db import obtener_factura

router = APIRouter(prefix="/api", tags=["email"])


class EmailRequest(BaseModel):
    receipt_id: str
    email: str


@router.post("/enviar_email")
def api_enviar_email(req: EmailRequest):

    # ---------------------------
    # 1) obtener factura del JSON
    # ---------------------------
    factura = obtener_factura(req.receipt_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada en la base de datos.")

    drive_url = factura.get("drive_url")
    if not drive_url:
        raise HTTPException(400, "La factura no tiene URL de Google Drive.")

    # ---------------------------
    # 2) descargar PDF desde Drive
    # ---------------------------
    try:
        r = httpx.get(drive_url)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        raise HTTPException(500, f"No se pudo descargar el PDF: {e}")

    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    # ---------------------------
    # 3) enviar con BREVO API
    # ---------------------------
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
    if not BREVO_API_KEY:
        raise HTTPException(500, "BREVO_API_KEY no está configurada en Render.")

    # remitente -> tu Gmail verificado dentro de Brevo
    FROM_EMAIL = "topfundasbb@gmail.com"

    payload = {
        "sender": {"name": "Top Fundas", "email": FROM_EMAIL},
        "to": [{"email": req.email}],
        "subject": f"Factura de compra - Top Fundas",
        "htmlContent": """
            <p>Hola! 👋</p>
            <p>Te enviamos la factura correspondiente a tu compra en <strong>Top Fundas</strong>.</p>
            <p>Muchas gracias por elegirnos</p>
        """,
        "attachment": [
            {
                "name": f"Factura_{factura['cbte_nro']}.pdf",
                "content": pdf_b64
            }
        ],
    }

    try:
        r = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=20
        )
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(500, f"Error enviando email vía Brevo: {e}")

    return {"status": "ok", "message": f"Email enviado a {req.email}"}
