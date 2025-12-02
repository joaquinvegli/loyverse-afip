# email_api.py

import base64
import os
import smtplib
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email import encoders

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
# 2) ENVIAR EMAIL (GMAIL SMTP)
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
    try:
        # El drive_url ya es un link directo tipo "uc?id=...&export=download"
        r = httpx.get(drive_url, timeout=30)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo descargar el PDF desde Drive: {e}"
        )

    # ----------------------------------------
    # 3) Preparar SMTP de Gmail
    # ----------------------------------------
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_pass:
        raise HTTPException(
            status_code=500,
            detail="Faltan GMAIL_USER o GMAIL_APP_PASSWORD en variables de entorno"
        )

    # ----------------------------------------
    # 4) Armar el correo con adjunto
    # ----------------------------------------
    asunto = "Factura de compra - Top Fundas"
    cuerpo = (
        "Hola! 👋\n\n"
        "Te enviamos la factura correspondiente a tu compra en Top Fundas.\n\n"
        "Muchas gracias por elegirnos.\n\n"
        "— Top Fundas"
    )

    msg = MIMEMultipart()
    msg["From"] = f"Top Fundas <{gmail_user}>"
    msg["To"] = req.email
    msg["Subject"] = asunto

    # Cuerpo en texto plano
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    # Adjunto PDF
    filename = f"Factura_{factura['cbte_nro']}.pdf"
    part = MIMEBase("application", "pdf")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    # ----------------------------------------
    # 5) Enviar correo por SMTP (Gmail)
    # ----------------------------------------
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()  # TLS
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, [req.email], msg.as_string())
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error enviando email por Gmail SMTP: {e}"
        )

    return {
        "status": "ok",
        "message": f"Email enviado correctamente a {req.email}",
    }
