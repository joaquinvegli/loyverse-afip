from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from loyverse_api import router as ventas_router

app = FastAPI()

# 🔴 ESTO ES OBLIGATORIO
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # después lo restringimos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ventas_router)

@app.get("/")
def root():
    return {"status": "ok"}
