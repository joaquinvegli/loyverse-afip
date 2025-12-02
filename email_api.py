# email_api.py
import os
import base64
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from json_db import obtener_factura, listado_facturas

router = APIRouter(prefix="/api", tags=["email"])

# ================================================
# MODELO REQUEST
# ================================================
class EmailRequest(BaseModel):
    receipt_id: str
    email: str


# ================================================
# LISTAR FACTURAS
# ================================================
@router.get("/facturas")
def api_listar_facturas():
    return {"facturas": listado_facturas()}


# ================================================
# ENVIAR EMAIL (BREVO)
# ================================================
@router.post("/enviar_email")
def api_enviar_email(req: EmailRequest):

    # -------------------------
    # 1) Buscar datos factura
    # -------------------------
    factura = obtener_factura(req.receipt_id)
    if not factura:
        raise HTTPException(404, f"No existe factura para receipt_id {req.receipt_id}")

    drive_url = factura.get("drive_url")
    if not drive_url:
        raise HTTPException(400, "La factura no tiene URL de Google Drive")

    # -------------------------
    # 2) Armar link directo a PDF (FIX REEMPLAZADO)
    # -------------------------

    # Ejemplos válidos:
    # https://drive.google.com/file/d/FILEID/view?usp=drive_link
    # → https://drive.google.com/uc?id=FILEID&export=download

    try:
        if "file/d/" in drive_url:
            file_id = drive_url.split("file/d/")[1].split("/")[0]
        elif "id=" in drive_url:
            file_id = drive_url.split("id=")[1].split("&")[0]
        else:
            raise Exception("Formato inesperado de URL de Drive")

        drive_direct_url = f"https://drive.google.com/uc?id={file_id}&export=download"
    except Exception as e:
        raise HTTPException(
            500,
            f"No se pudo procesar la URL de Drive ({drive_url}): {e}"
        )

    # -------------------------
    # 3) Descargar el PDF
    # -------------------------
    try:
        r = httpx.get(drive_direct_url, follow_redirects=True)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        raise HTTPException(
            500,
            f"No se pudo descargar el PDF desde Drive (URL: {drive_direct_url}): {e}"
        )

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    # -------------------------
    # 4) Enviar email via BREVO API
    # -------------------------
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY")

    if not BREVO_API_KEY:
        raise HTTPException(500, "Falta BREVO_API_KEY en Render")

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY,
    }

    payload = {
        "sender": {
            "name": "Top Fundas",
            "email": "topfundasbb@gmail.com"
        },
        "to": [
            {"email": req.email}
        ],
        "subject": "Factura de compra - Top Fundas",
        "htmlContent": """
            <p>Hola! 👋</p>
            <p>Te enviamos la factura correspondiente a tu compra en <strong>Top Fundas</strong>.</p>
            <p>Muchas gracias por elegirnos ❤️</p>
        """,
        "attachment": [
            {
                "content": pdf_b64,
                "name": f"Factura_{factura['cbte_nro']}.pdf"
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
        "message": f"Email enviado a {req.email}",
        "brevo_response": response.json()
    }
