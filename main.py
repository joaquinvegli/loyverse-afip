from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from loyverse_api import router as ventas_router
from facturar_api import router as facturar_router  # 🔥 FALTABA ESTO

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # después lo restringimos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(ventas_router)
app.include_router(facturar_router)  # 🔥 Y ESTO

@app.get("/")
def root():
    return {"status": "ok"}
