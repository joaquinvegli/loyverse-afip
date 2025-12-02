# email_api.py
import base64
import httpx
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from json_db import obtener_factura, listado_facturas

router = APIRouter(prefix="/api", tags=["email"])

# ===========================
# MODELO
# ===========================
class EmailRequest(BaseModel):
    receipt_id: str
    email: str


# ===========================
# LISTAR FACTURAS
# ===========================
@router.get("/facturas")
def api_listar_facturas():
    return {"facturas": listado_facturas()}


# ===========================
# ENVIAR EMAIL (BREVO API)
# ===========================
@router.post("/enviar_email")
def api_enviar_email(req: EmailRequest):

    # ----------------------------------------
    # 1) Buscar factura
    # ----------------------------------------
    factura = obtener_factura(req.receipt_id)
    if not factura:
        raise HTTPException(
            404,
            f"No existe factura registrada para receipt_id {req.receipt_id}"
        )

    drive_url = factura.get("drive_url")
    if not drive_url:
        raise HTTPException(400, "Factura sin drive_url")

    # ----------------------------------------
    # 2) Descargar PDF desde Drive
    # ----------------------------------------
    try:
        r = httpx.get(drive_url, timeout=30)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        raise HTTPException(500, f"No se pudo descargar PDF: {e}")

    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    # ----------------------------------------
    # 3) API Key de Brevo
    # ----------------------------------------
    API_KEY = os.environ.get("BREVO_API_KEY")
    if not API_KEY:
        raise HTTPException(500, "Falta BREVO_API_KEY en environment variables")

    headers = {
        "accept": "application/json",
        "api-key": API_KEY,
        "content-type": "application/json",
    }

    # ----------------------------------------
    # 4) Payload
    # ----------------------------------------
    payload = {
        "sender": {
            "name": "Top Fundas",
            "email": "topfundasbb@gmail.com"
        },
        "to": [{"email": req.email}],
        "subject": "Factura de compra - Top Fundas",
        "htmlContent": """
            <p>¡Gracias por tu compra en <strong>Top Fundas</strong>!</p>
            <p>Adjuntamos tu factura.</p>
            <p>Saludos,<br>Top Fundas</p>
        """,
        "attachment": [
            {
                "content": pdf_b64,
                "name": f"Factura_{factura['cbte_nro']}.pdf"
            }
        ]
    }

    # ----------------------------------------
    # 5) Enviar email via API
    # ----------------------------------------
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
            detail=f"Error enviando email con Brevo: {e}"
        )

    return {
        "status": "ok",
        "message": f"Email enviado correctamente a {req.email}",
        "brevo_response": response.json()
    }
