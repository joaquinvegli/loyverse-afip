from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from loyverse_api import router as ventas_router
from facturar_api import router as facturar_router
from email_api import router as email_router
from nota_credito_api import router as nota_credito_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ventas_router)
app.include_router(facturar_router)
app.include_router(email_router)
app.include_router(nota_credito_router)

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug/recibo/{receipt_id}")
async def debug_recibo(receipt_id: str):
    import httpx
    import os
    token = os.environ.get("LOYVERSE_TOKEN")
    url = f"https://api.loyverse.com/v1.0/receipts?receipt_number={receipt_id}&expand=customer"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        return r.json()
