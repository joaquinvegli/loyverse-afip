# email_api.py
import base64
import os
import httpx
import smtplib
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from json_db import obtener_factura

router = APIRouter(prefix="/api", tags=["email"])

class EmailRequest(BaseModel):
    receipt_id: str
    email: str


@router.post("/enviar_email")
def enviar_email(req: EmailRequest):

    # ===============================
    # 1) Buscar factura en el JSON
    # ===============================
    factura = obtener_factura(req.receipt_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada en DB")

    drive_url = factura.get("drive_url")
    if not drive_url:
        raise HTTPException(400, "La factura no tiene drive_url")

    # ===============================
    # 2) Descargar PDF de Drive
    # ===============================
    try:
        r = httpx.get(drive_url, follow_redirects=True)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        raise HTTPException(500, f"No se pudo descargar el PDF: {e}")

    # ===============================
    # 3) Preparar credenciales SMTP
    # ===============================

    gmail_user = os.getenv("GMAIL_USER")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_pass:
        raise HTTPException(500, "Faltan variables SMTP: GMAIL_USER o GMAIL_APP_PASSWORD")

    # ===============================
    # 4) Construir el email
    # ===============================
    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = req.email
    msg["Subject"] = "Factura de compra - Top Fundas"

    cuerpo = """
Hola! 👋

Te enviamos la factura correspondiente a tu compra en Top Fundas.

¡Muchas gracias por elegirnos! 🙌
"""

    msg.attach(MIMEText(cuerpo, "plain"))

    # Adjuntar PDF
    part = MIMEBase("application", "octet-stream")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename=Factura_{factura['cbte_nro']}.pdf")
    msg.attach(part)

    # ===============================
    # 5) Enviar email via SMTP
    # ===============================

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, req.email, msg.as_string())
        server.quit()
    except Exception as e:
        raise HTTPException(500, f"Error enviando email via SMTP: {e}")

    return {"status": "ok", "message": f"Email enviado a {req.email}"}
