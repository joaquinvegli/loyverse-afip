from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from json_db import obtener_factura
from email_utils import enviar_email_factura  # asumimos que ya existe

router = APIRouter(prefix="/api", tags=["email"])


# ===============================
# MODELO REQUEST
# ===============================
class EnviarEmailRequest(BaseModel):
    receipt_id: str
    email: str


# ===============================
# ENVIAR FACTURA POR MAIL
# ===============================
@router.post("/enviar_email")
async def enviar_email(data: EnviarEmailRequest):
    factura = obtener_factura(data.receipt_id)

    if not factura:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    if not data.email or "@" not in data.email:
        raise HTTPException(status_code=400, detail="Email inválido")

    try:
        enviar_email_factura(
            email_destino=data.email,
            factura=factura,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ok"}
