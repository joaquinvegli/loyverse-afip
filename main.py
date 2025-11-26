from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loyverse import get_receipts, get_receipt
from afip import test_afip_connection

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok", "message": "API funcionando"}

@app.get("/test/loyverse")
async def test_loyverse():
    try:
        return {"status": "ok", "data": await get_receipts()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/test/loyverse/{receipt_id}")
async def test_receipt(receipt_id: str):
    try:
        return {"status": "ok", "data": await get_receipt(receipt_id)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/test/afip")
def test_afip():
    result = test_afip_connection()
    return result
