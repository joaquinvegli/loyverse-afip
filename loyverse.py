import httpx
import os

LOYVERSE_URL = "https://api.loyverse.com/v1.0"
LOYVERSE_TOKEN = os.getenv("LOYVERSE_TOKEN")  # Lo cargaremos en Render como variable de entorno

headers = {
    "Authorization": f"Bearer {LOYVERSE_TOKEN}"
}

async def get_receipts():
    """
    Devuelve la lista de recibos (ventas) de Loyverse.
    Por ahora leeremos los últimos 50 como prueba.
    """
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{LOYVERSE_URL}/receipts", headers=headers)
        res.raise_for_status()
        return res.json()

async def get_receipt(receipt_id):
    """
    Devuelve un recibo específico por ID.
    """
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{LOYVERSE_URL}/receipts/{receipt_id}", headers=headers)
        res.raise_for_status()
        return res.json()
