# main.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from afip import test_afip_connection

# Routers de módulos
from debug import router as debug_router
from loyverse_api import router as loyverse_router
from loyverse_debug import router as loyverse_debug_router
from facturar_api import router as facturar_router   # ← NUEVO, IMPORTANTE


app = FastAPI()


# ======================================================
# CORS (permitir frontend StackBlitz)
# ======================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================================================
# ENDPOINT BÁSICO
# ======================================================
@app.get("/")
def root():
    return {"status": "ok", "message": "API funcionando"}


# ======================================================
# TEST AFIP
# ======================================================
@app.get("/test/afip")
def test_afip():
    try:
        result = test_afip_connection()
        return {"status": "ok", "data": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ======================================================
# DEBUG ARCHIVOS AFIP
# ======================================================
@app.get("/debug/afip-files")
def debug_files():
    try:
        with open("/etc/secrets/afip_new.key", "rb") as f:
            key_bytes = f.read()

        with open("/etc/secrets/afip_new.crt", "rb") as f:
            crt_bytes = f.read()

        return {
            "key_first_bytes": list(key_bytes[:20]),
            "crt_first_bytes": list(crt_bytes[:20]),
            "key_text_start": key_bytes[:200].decode("latin1", errors="replace"),
            "crt_text_start": crt_bytes[:200].decode("latin1", errors="replace"),
        }
    except Exception as e:
        return {"error": str(e)}


# ======================================================
# INCLUIR ROUTERS
# ======================================================
app.include_router(debug_router)
app.include_router(loyverse_router)
app.include_router(loyverse_debug_router)
app.include_router(facturar_router)   # ← ESTO ES IMPORTANTE


# ======================================================
# DEBUG AFIP WSDL
# ======================================================
@app.get("/debug/wsdl2")
def debug_wsdl2():
    import traceback
    import requests
    url = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"
    try:
        r = requests.get(url, timeout=10)
        return {
            "status": r.status_code,
            "headers": dict(r.headers),
            "first_200": r.text[:200],
        }
    except Exception as e:
        return {
            "error": str(e),
            "typ
