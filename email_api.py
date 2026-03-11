# email_api.py
import os
import base64
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from json_db import obtener_factura, obtener_nota_credito

router = APIRouter(prefix="/api", tags=["email"])


class EmailRequest(BaseModel):
    receipt_id: str
    email: str


@router.post("/enviar_email")
def api_enviar_email(req: EmailRequest):

    receipt_id = req.receipt_id
    email = req.email.strip()

    if not email:
        raise HTTPException(400, "Email inválido")

    # 1) Buscar comprobante
    comprobante = obtener_factura(receipt_id)
    tipo = "FACTURA"

    if not comprobante:
        comprobante = obtener_nota_credito(receipt_id)
        tipo = "NOTA DE CREDITO"

    if not comprobante:
        raise HTTPException(404, f"No existe factura ni nota de crédito para receipt_id {receipt_id}")

    drive_url = comprobante.get("drive_url")
    if not drive_url:
        raise HTTPException(400, "El comprobante no tiene URL del PDF")

    # 2) Descargar el PDF directamente desde la URL de Supabase
    try:
        print(f"DEBUG email → Descargando PDF desde: {drive_url}")
        r = httpx.get(drive_url, timeout=30, follow_redirects=True)
        r.raise_for_status()
        pdf_bytes = r.content
        print(f"DEBUG email → PDF descargado OK, tamaño: {len(pdf_bytes)} bytes")
    except Exception as e:
        print(f"ERROR email → No se pudo descargar el PDF: {e}")
        raise HTTPException(500, f"No se pudo descargar el PDF: {e}")

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    # 3) Enviar con Brevo
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
        subject = f"Factura C N° {comprobante.get('cbte_nro', '')} - Top Fundas"
        html_content = """
            <p>Hola 👋</p>
            <p>Te enviamos la <strong>factura</strong> correspondiente a tu compra en <strong>Top Fundas</strong>.</p>
            <p>Muchas gracias por elegirnos ❤️</p>
        """
        filename = f"FACT-C-{comprobante.get('pto_vta', '0004'):04d}-{comprobante.get('cbte_nro', 0):08d}.pdf"

    payload = {
        "sender": {"name": "Top Fundas", "email": "topfundasbb@gmail.com"},
        "to": [{"email": email}],
        "subject": subject,
        "htmlContent": html_content,
        "attachment": [{"content": pdf_b64, "name": filename}],
    }

    try:
        print(f"DEBUG email → Enviando mail a {email} via Brevo")
        response = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers=headers,
            json=payload,
            timeout=30,
        )
        print(f"DEBUG email → Brevo respondió: {response.status_code} - {response.text}")
        response.raise_for_status()
    except Exception as e:
        print(f"ERROR email → Brevo falló: {e}")
        raise HTTPException(500, f"Error enviando email con Brevo: {e}")

    return {
        "status": "ok",
        "message": f"{tipo} enviada por email a {email}",
    }
