# email_api.py
import base64
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from json_db import obtener_factura, listado_facturas

router = APIRouter(prefix="/api", tags=["email"])

# ===========================
# MODELOS
# ===========================
class EmailRequest(BaseModel):
    receipt_id: str
    email: str


# ===========================
# 1) LISTAR FACTURAS
# ===========================
@router.get("/facturas")
def api_listar_facturas():
    """
    Devuelve todas las facturas registradas en facturas_db.json
    """
    db = listado_facturas()
    return {"facturas": db}


# ===========================
# 2) ENVIAR EMAIL
# ===========================
@router.post("/enviar_email")
def api_enviar_email(req: EmailRequest):

    # ----------------------------------------
    # 1) Buscar datos de la factura en JSON
    # ----------------------------------------
    factura = obtener_factura(req.receipt_id)
    if not factura:
        raise HTTPException(
            status_code=404,
            detail=f"No existe factura registrada para receipt_id {req.receipt_id}"
        )

    drive_url = factura.get("drive_url")
    if not drive_url:
        raise HTTPException(
            status_code=400,
            detail="La factura no tiene drive_url guardado. No se puede adjuntar PDF."
        )

    # ----------------------------------------
    # 2) Descargar el PDF desde Google Drive
    # ----------------------------------------
    # Link directo a archivo PDF
    # https://drive.google.com/uc?id=<ID>&export=download
    try:
        drive_direct_url = drive_url.replace("export=download", "export=download")
        r = httpx.get(drive_direct_url)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo descargar el PDF desde Drive: {e}"
        )

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    # ----------------------------------------
    # 3) Preparar cuerpo del email
    # ----------------------------------------
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

    if not RESEND_API_KEY:
        raise HTTPException(500, "Falta RESEND_API_KEY en las environment variables")

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    asunto = f"Factura de compra - Top Fundas"
    cuerpo = (
        "Hola! 👋\n\n"
        "Te enviamos la factura correspondiente a tu compra en Top Fundas.\n\n"
        "Muchas gracias por elegirnos.\n\n"
        "— Top Fundas"
    )

    payload = {
        "from": "Top Fundas <on-behalf-of@resend.dev>",
        "to": req.email,
        "subject": asunto,
        "text": cuerpo,
        "attachments": [
            {
                "filename": f"Factura_{factura['cbte_nro']}.pdf",
                "content": pdf_b64,
                "type": "application/pdf"
            }
        ]
    }

    # ----------------------------------------
    # 4) Llamar a la API de Resend
    # ----------------------------------------
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error enviando email con Resend: {e}"
        )

    return {
        "status": "ok",
        "message": f"Email enviado correctamente a {req.email}",
        "resend_response": response.json()
    }
