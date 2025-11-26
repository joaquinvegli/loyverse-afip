from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loyverse import get_receipts, get_receipt
from afip import facturar_prueba

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

@app.get("/test/afip")
def test_afip():
    try:
        result = facturar_prueba()
        return {"status": "ok", "factura": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/debug/key")
def debug_key():
    key = os.environ.get("AFIP_CERT_KEY", "")
    return {
        "len": len(key),
        "preview_start": key[:80],
        "preview_end": key[-80:],
        "contains_literal_n": "\\n" in key,
        "lines": key.count("\n")
    }
