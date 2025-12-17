from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from loyverse_api import router as ventas_router
# ❌ NO importar email_api

app = FastAPI()

# CORS (igual que antes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ SOLO routers que existen y funcionaban
app.include_router(ventas_router)

@app.get("/")
def root():
    return {"status": "ok"}
