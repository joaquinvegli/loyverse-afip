from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loyverse import get_receipts, get_receipt

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok", "message": "API funcionando"}

@app.get("/test/loyverse")
async def test_loyverse():
    try:
        data = await get_receipts()
        return {"status": "ok", "data": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/test/loyverse/{receipt_id}")
async def test_receipt(receipt_id: str):
    try:
        data = await get_receipt(receipt_id)
        return {"status": "ok", "data": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# Endpoint para AFIP se elimina porque facturar_prueba() ya no existe.
# Si querés uno nuevo para probar AFIP, avisame y lo agrego con la función correcta.
