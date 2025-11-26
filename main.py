from fastapi import FastAPI
from fastapi.responses import JSONResponse
from afip import test_afip_connection

app = FastAPI()


@app.get("/")
def root():
    return {"status": "ok", "message": "API funcionando"}


@app.get("/test/afip")
def test_afip():
    """
    Prueba completa usando PyAfipWS (afip.py).
    """
    try:
        result = test_afip_connection()
        return {"status": "ok", "data": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/debug/afip-files")
def debug_files():
    """
    Muestra los primeros bytes de los archivos de certificados/keys
    que estás usando realmente (afip_new.*).
    """
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


# Si tenés un router extra en debug.py lo seguimos incluyendo
from debug import router as debug_router
app.include_router(debug_router)


@app.get("/debug/wsdl2")
def debug_wsdl2():
    """
    Verifica que se pueda descargar el WSDL de AFIP y que 'requests' funcione.
    """
    import traceback
    import requests

    url = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"
    try:
        r = requests.get(url, timeout=10)
        return {
            "status": r.status_code,
            "headers": dict(r.headers),
            "first_200": r.text[:200]
        }
    except Exception as e:
        return {
            "error": str(e),
            "type": str(type(e)),
            "trace": traceback.format_exc()
        }


@app.get("/debug/imports")
def debug_imports():
    """
    Verifica que el módulo 'requests' esté instalado y accesible.
    """
    try:
        import requests
        return {"status": "ok", "requests_version": requests.__version__}
    except Exception as e:
        return {"error": str(e)}


@app.get("/debug/login_raw")
def debug_login_raw():
    """
    Prueba de conexión directa al WSAA de AFIP sin PyAfipWS:
    - Genera el CMS con openssl (DER binario)
    - Lo pasa a base64
    - Lo manda dentro de un sobre SOAP (como AFIP exige)
    Esto sirve para ver si el certificado, la clave y la conexión están OK.
    """
    import os
    import subprocess
    import tempfile
    import requests
    import base64

    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        return {"error": f"NO existe {key_path}"}

    if not os.path.exists(crt_path):
        return {"error": f"NO existe {crt_path}"}

    # 1) XML del loginTicketRequest (puede ajustarse luego para fechas dinámicas)
    xml_data = """<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>1</uniqueId>
    <generationTime>2025-01-01T00:00:00-03:00</generationTime>
    <expirationTime>2030-01-01T00:00:00-03:00</expirationTime>
  </header>
  <service>wsfe</service>
</loginTicketRequest>
"""

    with tempfile.TemporaryDirectory() as tmp:
        req_xml = os.path.join(tmp, "req.xml")
        cms_der = os.path.join(tmp, "req.cms")

        # Guardamos el XML
        with open(req_xml, "_
