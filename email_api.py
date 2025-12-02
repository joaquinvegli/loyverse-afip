# email_api.py
import base64
import httpx
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from json_db import obtener_factura

router = APIRouter(prefix="/api", tags=["email"])

class EmailRequest(BaseModel):
    receipt_id: str
    email: str


def extract_drive_file_id(drive_url: str) -> str:
    """
    Extrae el file_id desde un URL de Drive típico:
    https://drive.google.com/uc?id=XXXX&export=download
    """
    import urllib.parse as urlparse

    parsed = urlparse.urlparse(drive_url)
    query = urlparse.parse_qs(parsed.query)
    file_id = query.get("id", [None])[0]

    if not file_id:
        raise ValueError("No se pudo extraer el file_id desde drive_url")

    return file_id


@router.post("/enviar_email")
def api_enviar_email(req: EmailRequest):
    # 1) Obtener factura
    factura = obtener_factura(req.receipt_id)
    if not factura:
        raise HTTPException(404, f"No existe factura para receipt_id {req.receipt_id}")

    drive_url = factura.get("drive_url")
    if not drive_url:
        raise HTTPException(400, "La factura no tiene drive_url guardado")

    # 2) Extraer file_id y armar URL directa
    try:
        file_id = extract_drive_file_id(drive_url)
        direct_url = f"https://drive.usercontent.google.com/download?id={file_id}"
    except Exception as e:
        raise HTTPException(500, f"No se pudo extraer file_id de Google Drive: {e}")

    # 3) Descargar PDF (sin redirecciones)
    try:
        r = httpx.get(direct_url, follow_redirects=True)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        raise HTTPException(
            500,
            f"No se pudo descargar el PDF desde Google Drive (direct_url): {str(e)}"
        )

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    # 4) Enviar con Brevo
    BREVO_API_KEY = os.getenv("BREVO_API_KEY")
    if not BREVO_API_KEY:
        raise HTTPException(500, "Falta BREVO_API_KEY")

    payload = {
        "sender": {
            "name": "Top Fundas",
            "email": "noreply@topfundas.com"  # usarás el que configuraste en Brevo
        },
        "to": [
            {"email": req.email}
        ],
        "subject": "Factura de compra - Top Fundas",
        "htmlContent": """
            <p>Hola 👋</p>
            <p>Te enviamos la factura correspondiente a tu compra.</p>
            <p>¡Gracias por elegir Top Fundas!</p>
        """,
        "attachment": [
            {
                "content": pdf_b64,
                "name": f"Factura_{factura['cbte_nro']}.pdf"
            }
        ]
    }

    try:
        resp = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json"
            },
            json=payload
        )
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(500, f"Error enviando email con Brevo: {e}")

    return {"status": "ok", "message": f"Email enviado a {req.email}"}
