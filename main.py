from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os

# Routers externos
from debug import router as debug_router
from loyverse_api import router as loyverse_router
from loyverse_debug import router as loyverse_debug_router
from facturar_api import router as facturar_router


app = FastAPI()


# ============================================================
# CORS PARA PERMITIR FRONTEND
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # FIX PARA STACKBLITZ
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ROOT
# ============================================================
@app.get("/")
def root():
    return {"status": "ok", "message": "API funcionando"}


# ============================================================
# DEBUG ARCHIVOS CERTIFICADOS
# ============================================================
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


# ============================================================
# INCLUIR ROUTERS
# ============================================================
app.include_router(debug_router)
app.include_router(loyverse_router)
app.include_router(loyverse_debug_router)
app.include_router(facturar_router)


# ============================================================
# DEBUG WSDL AFIP
# ============================================================
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


# ============================================================
# DEBUG IMPORT REQUESTS
# ============================================================
@app.get("/debug/imports")
def debug_imports():
    try:
        import requests
        return {"status": "ok", "requests_version": requests.__version__}
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# DEBUG LOGIN AFIP RAW
# ============================================================
@app.get("/debug/login_raw")
def debug_login_raw():
    import os
    import subprocess
    import tempfile
    import requests
    import base64
    from datetime import datetime, timedelta, timezone

    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        return {"error": f"NO existe {key_path}"}
    if not os.path.exists(crt_path):
        return {"error": f"NO existe {crt_path}"}

    TZ = timezone(timedelta(hours=-3))
    now = datetime.now(TZ)

    gen = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S%z")
    exp = (now + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S%z")

    generation_time = gen[:-2] + ":" + gen[-2:]
    expiration_time = exp[:-2] + ":" + exp[-2:]

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

    soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
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


# ============================================================
# DEBUG TIME SERVER
# ============================================================
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


# ============================================================
# DEBUG WSAA CLIENT
# ============================================================
@app.get("/debug/wsaa_client")
def debug_wsaa_client():
    from pyafipws.wsaa import WSAA
    import traceback

    wsaa = WSAA()
    wsaa.HOMO = False

    try:
        wsaa.AnalizarWSDL()
    except Exception as e:
        return {
            "error": f"No pudo cargar WSDL: {e}",
            "trace": traceback.format_exc(),
        }

    return {
        "status": "ok",
        "client_loaded": wsaa.client is not None,
        "client_type": str(type(wsaa.client)),
        "methods": dir(wsaa.client) if wsaa.client else None,
    }


# ============================================================
# DEBUG FILESYSTEM
# ============================================================

@app.get("/debug/list-root")
def list_root():
    return {
        "cwd": os.getcwd(),
        "root_files": os.listdir(".")
    }


@app.get("/debug/list-static")
def list_static():
    if os.path.exists("static"):
        return {
            "exists": True,
            "files": os.listdir("static")
        }
    else:
        return {"exists": False}


@app.get("/debug/check-logo")
def check_logo():
    path = "static/logo.jpg"
    return {
        "exists": os.path.exists(path),
        "absolute_path": os.path.abspath(path),
        "cwd": os.getcwd()
    }


@app.get("/debug/static-full")
def debug_static_full():
    folder = "static"
    if not os.path.exists(folder):
        return {"exists": False, "error": "Carpeta static NO existe en este entorno."}

    archivos = []
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        info = {
            "name": filename,
            "is_file": os.path.isfile(path),
            "size_bytes": os.path.getsize(path),
            "absolute_path": os.path.abspath(path)
        }
        archivos.append(info)

    return {
        "exists": True,
        "cwd": os.getcwd(),
        "static_path": os.path.abspath(folder),
        "files": archivos,
    }


# ============================================================
# NUEVO: MOSTRAR EL CONTENIDO REAL DE pdf_afip.py
# ============================================================
@app.get("/debug/show-pdf-code")
def debug_show_pdf_code():
    try:
        with open("pdf_afip.py", "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except Exception as e:
        return {"error": str(e)}
@app.get("/debug/where-pdf")
def where_pdf():
    import os
    return {
        "working_dir": os.getcwd(),
        "exists_in_cwd": os.path.exists("pdf_afip.py"),
        "exists_in_src": os.path.exists("/opt/render/project/src/pdf_afip.py"),
        "exists_in_root": os.path.exists("/pdf_afip.py"),
        "files_in_cwd": os.listdir("."),
        "files_in_src": os.listdir("/opt/render/project/src")
    }

@app.get("/debug/clear-pycache")
def clear_pycache():
    import os, shutil
    removed = []
    for root, dirs, files in os.walk("/opt/render/project/src"):
        for d in dirs:
            if d == "__pycache__":
                full = os.path.join(root, d)
                shutil.rmtree(full)
                removed.append(full)
    return {"removed": removed}

