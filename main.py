from fastapi import FastAPI

from loyverse_api import router as ventas_router
from nota_credito_api import router as nota_credito_router

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok", "message": "API funcionando"}

app.include_router(ventas_router)
app.include_router(nota_credito_router)
