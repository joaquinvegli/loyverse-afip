# email_api.py
import base64
import httpx
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from json_db import obtener_factura

router = APIRouter(prefix="/api", tags=["email"])


# ===========================
# MODELO
# ===========================
class EmailRequest(BaseModel):
    receipt_id: str
    email: str


# ===========================
# ENVIAR EMAIL (BREVO API)
# ===========================
@router.post("/enviar_email")
def api_enviar_email(req: EmailRequest):

    # ----------------------------------------
    # 1) Buscar datos de la factura
    # ----------------------------------------
    factura = obtener_factura(req.receipt_id)
    if not factura:
        raise HTTPException(
            404,
            f"No existe factura registrada para receipt_id {req.receipt_id}"
        )

    drive_url = factura.get("drive_url")
    if not drive_url:
        raise HTTPException(
            400,
            "La factura no tiene drive_url guardado. No se puede adjuntar PDF."
        )

    # ----------------------------------------
    # 2) Descargar PDF desde Drive
    # ----------------------------------------
    try:
        r = httpx.get(drive_url)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        raise HTTPException(
            500,
            f"No se pudo descargar el PDF desde Drive: {e}"
        )

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    # ----------------------------------------
    # 3) BREVO API KEY
    # ----------------------------------------
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY")

    if not BREVO_API_KEY:
        raise HTTPException(
            500,
            "Falta BREVO_API_KEY en Render"
        )

    # ----------------------------------------
    # 4) Preparar payload BREVO
    # ----------------------------------------
    payload = {
        "sender": {
            "name": "Top Fundas",
            "email": "topfundasbb@gmail.com"   # Remitente validado en Brevo
        },
        "to": [
            {"email": req.email}
        ],
        "subject": f"Factura de compra - Top Fundas",
        "htmlContent": """
            <h2>Gracias por tu compra en Top Fundas 💙</h2>
            <p>Adjuntamos la factura correspondiente a tu compra.</p>
            <p>¡Gracias por elegirnos!</p>
        """,
        "attachment": [
            {
                "name": f"Factura_{factura['cbte_nro']}.pdf",
                "content": pdf_b64
            }
        ]
    }

    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json"
    }

    # ----------------------------------------
    # 5) Enviar email via BREVO API
    # ----------------------------------------
    try:
        res = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=30
        )
        res.raise_for_status()
    except Exception as e:
        raise HTTPException(
            500,
            f"Error enviando email con Brevo: {e}"
        )

    return {
        "status": "ok",
        "message": f"Email enviado correctamente a {req.email}"
    }
