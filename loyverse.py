import httpx
import os

BASE_URL = "https://api.loyverse.com/v1.0"
TOKEN = os.environ.get("LOYVERSE_TOKEN")

if not TOKEN:
    raise Exception("LOYVERSE_TOKEN no está definida en Environment Variables")


async def get_receipts():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/receipts", headers=headers)
        r.raise_for_status()
        return r.json()


async def get_receipt(receipt_id: str):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/receipts/{receipt_id}", headers=headers)
        r.raise_for_status()
        return r.json()
