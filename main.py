from fastapi import FastAPI
from fastapi.responses import JSONResponse
import os
from loyverse import get_receipts, get_receipt

app = FastAPI()

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "API Loyverse-AFIP funcionando (modo prueba)"
    }

@app.get("/test/loyverse")
async def test_loyverse():
    """
    Endpoint de prueba para leer ventas desde Loyverse.
    """
    try:
        data = await get_receipts()
        return JSONResponse(content={"status": "ok", "data": data})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/test/loyverse/{receipt_id}")
async def test_receipt(receipt_id: str):
    """
    Leer un recibo específico por ID desde Loyverse.
    """
    try:
        data = await get_receipt(receipt_id)
        return JSONResponse(content={"status": "ok", "data": data})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
