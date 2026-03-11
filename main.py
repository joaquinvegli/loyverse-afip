from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Routers
from loyverse_api import router as ventas_router
from facturar_api import router as facturar_router
from email_api import router as email_router  # ✅ agregar

app = FastAPI()

# ==============================
# CORS (obligatorio para frontend)
# ==============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # luego se puede restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================
# Rutas API
# ==============================
app.include_router(ventas_router)      # /api/ventas
app.include_router(facturar_router)    # /api/facturar
app.include_router(email_router)       # /api/enviar_email ✅

# ==============================
# Health check
# ==============================
@app.get("/")
def root():
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
