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
