# email_api.py
import os
import base64
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from json_db import obtener_factura

router = APIRouter(prefix="/api", tags=["email"])

# =====================================================
# MODELO REQUEST
# =====================================================
class EmailRequest(BaseModel):
    receipt_id: str
    email: str


# =====================================================
# ENVIAR EMAIL CON RESEND
# =====================================================
@router.post("/enviar_email")
def api_enviar_email(req: EmailRequest):

    # ================================
    # 1) BUSCAR FACTURA EN JSON DB
    # ================================
    factura = obtener_factura(req.receipt_id)
    if not factura:
        raise HTTPException(404, f"No existe factura para receipt_id {req.receipt_id}")

    drive_url = factura.get("drive_url")
    if not drive_url:
        raise HTTPException(400, "La factura no tiene drive_url guardado")

    # ================================
    # 2) DESCARGAR EL PDF DE DRIVE
    # ================================
    try:
        r = httpx.get(drive_url, follow_redirects=True, timeout=30)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        raise HTTPException(500, f"No se pudo descargar el PDF desde Drive: {e}")

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    # ================================
    # 3) PREPARAR EMAIL
    # ================================
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
    if not RESEND_API_KEY:
        raise HTTPException(500, "Falta RESEND_API_KEY en las env variables")

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    subject = f"Factura de compra - Top Fundas"

    text_body = (
        "Hola! 👋\n\n"
        "Te enviamos la factura correspondiente a tu compra en Top Fundas.\n\n"
        "Muchas gracias por elegirnos 🙌\n\n"
        "— Top Fundas"
    )

    payload = {
        "from": "Top Fundas <onboarding@resend.dev>",
        "to": req.email,
        "subject": subject,
        "text": text_body,
        "attachments": [
            {
                "filename": f"Factura_{factura['cbte_nro']}.pdf",
                "content": pdf_b64,
                "type": "application/pdf",
            }
        ],
    }

    # ================================
    # 4) ENVIAR VIA RESEND
    # ================================
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers=headers,
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(500, f"Error enviando email con Resend: {e}")

    return {
        "status": "ok",
        "message": f"Email enviado correctamente a {req.email}",
        "resend_response": resp.json()
    }
