from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Routers
from loyverse_api import router as ventas_router
from facturar_api import router as facturar_router
from email_api import router as email_router

app = FastAPI()

# ===============================
# CORS (obligatorio para frontend)
# ===============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # luego si querés lo cerramos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# RUTAS
# ===============================
app.include_router(ventas_router)
app.include_router(facturar_router)
app.include_router(email_router)

# ===============================
# ROOT
# ===============================
@app.get("/")
def root():
    return {"status": "ok"}
