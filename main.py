from fastapi import FastAPI
from fastapi.responses import JSONResponse
from afip import test_afip_connection

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/test/afip")
def test_afip():
    try:
        result = test_afip_connection()
        return {"status": "ok", "afip": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
