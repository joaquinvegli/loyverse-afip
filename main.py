from fastapi import FastAPI
from fastapi.responses import JSONResponse
from afip import test_afip_connection

app = FastAPI()


@app.get("/")
def root():
    return {"status": "ok", "message": "API funcionando"}


@app.get("/test/afip")
def test_afip():
    try:
        result = test_afip_connection()
        return {"status": "ok", "data": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


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


from debug import router as debug_router
app.include_router(debug_router)


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
            "type": str(type(e)),
            "trace": traceback.format_exc(),
        }


@app.get("/debug/imports")
def debug_imports():
    try:
        import requests
        return {"status": "ok", "requests_version": requests.__version__}
    except Exception as e:
        return {"error": str(e)}


@app.get("/debug/login_raw")
def debug_login_raw():
    import os
    import subprocess
    import tempfile
    import requests
    import base64
    from datetime import datetime, timedelta

    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        return {"error": f"NO existe {key_path}"}

    if not os.path.exists(crt_path):
        return {"error": f"NO existe {crt_path}"}

    # Fechas dinámicas para AFIP
    generation_time = (datetime.utcnow() - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
    expiration_time = (datetime.utcnow() + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S")

    xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>1</uniqueId>
    <generationTime>{generation_time}</generationTime>
    <expirationTime>{expiration_time}</expirationTime>
  </header>
  <service>wsfe</service>
</loginTicketRequest>
"""

    with tempfile.TemporaryDirectory() as tmp:
        req_xml = os.path.join(tmp, "req.xml")
        cms_der = os.path.join(tmp, "req.cms")

        with open(req_xml, "w", encoding="utf-8") as f:
            f.write(xml_data)

        cmd = [
            "openssl", "smime", "-sign",
            "-binary",
            "-signer", crt_path,
            "-inkey", key_path,
            "-in", req_xml,
            "-out", cms_der,
            "-outform", "DER",
            "-nodetach",
        ]

        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0:
            return {
                "error": "OpenSSL error",
                "returncode": res.returncode,
                "stderr": res.stderr.decode(errors="ignore"),
            }

        with open(cms_der, "rb") as f:
            cms_bytes = f.read()

    cms_b64 = base64.b64encode(cms_bytes).decode()

   .soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <loginCms>
      <in0>{cms_b64}</in0>
    </loginCms>
  </soapenv:Body>
</soapenv:Envelope>
"""

    url = "https://wsaa.afip.gov.ar/ws/services/LoginCms"
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "",
    }

    try:
        resp = requests.post(url, data=soap_body.encode("utf-8"), headers=headers, timeout=20)
    except Exception as e:
        return {"error": f"request exception: {e}"}

    return {
        "http_status": resp.status_code,
        "text": resp.text[:4000],
    }


# -------------------------------
# NUEVO ENDPOINT CORRECTO AQUÍ
# -------------------------------
@app.get("/debug/server_time")
def debug_server_time():
    from datetime import datetime, timedelta

    now_local = datetime.now()
    now_utc = datetime.utcnow()
    now_utc_afip = now_utc - timedelta(hours=3)

    return {
        "server_local": now_local.strftime("%Y-%m-%d %H:%M:%S"),
        "server_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "afip_utc_minus3": now_utc_afip.strftime("%Y-%m-%d %H:%M:%S"),
        "diff_seconds": now_local.timestamp() - now_utc.timestamp(),
    }
