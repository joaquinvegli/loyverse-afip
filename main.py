from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# Routers externos
from debug import router as debug_router
from loyverse_api import router as loyverse_router
from loyverse_debug import router as loyverse_debug_router
from facturar_api import router as facturar_router
from email_api import router as email_router   # 👈 NUEVO

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
# INCLUIR ROUTERS
# ============================================================
app.include_router(debug_router)
app.include_router(loyverse_router)
app.include_router(loyverse_debug_router)
app.include_router(facturar_router)
app.include_router(email_router)  # 👈 NUEVO - API de emails y listado de facturas

# ============================================================
# DEBUG VARIOS
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
        return {"exists": True, "files": os.listdir("static")}
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
        return {"exists": False}

    archivos = []
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        archivos.append({
            "name": filename,
            "is_file": os.path.isfile(path),
            "size_bytes": os.path.getsize(path),
            "absolute_path": os.path.abspath(path),
        })

    return {
        "exists": True,
        "cwd": os.getcwd(),
        "static_path": os.path.abspath(folder),
        "files": archivos,
    }

@app.get("/debug/show-pdf-code")
def debug_show_pdf_code():
    try:
        with open("pdf_afip.py", "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except Exception as e:
        return {"error": str(e)}

@app.get("/debug/where-pdf")
def where_pdf():
    return {
        "working_dir": os.getcwd(),
        "exists_in_cwd": os.path.exists("pdf_afip.py"),
        "exists_in_src": os.path.exists("/opt/render/project/src/pdf_afip.py"),
        "exists_in_root": os.path.exists("/pdf_afip.py"),
        "files_in_cwd": os.listdir("."),
        "files_in_src": os.listdir("/opt/render/project/src"),
    }

@app.get("/debug/clear-pycache")
def clear_pycache():
    import shutil
    removed = []
    for root, dirs, files in os.walk("/opt/render/project/src"):
        for d in dirs:
            if d == "__pycache__":
                full = os.path.join(root, d)
                shutil.rmtree(full)
                removed.append(full)
    return {"removed": removed}

@app.get("/debug/test-logo")
def debug_test_logo():
    path = "static/logo_fixed.png"

    if not os.path.exists(path):
        return {"ok": False, "error": "NO existe el archivo", "path": os.path.abspath(path)}

    from reportlab.lib.utils import ImageReader

    try:
        img = ImageReader(path)
        w, h = img.getSize()
        return {"ok": True, "size": [w, h], "path": os.path.abspath(path)}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": os.path.abspath(path)}

# ============================================================
# NUEVO: VER DESDE DONDE SE CARGA pdf_afip.py
# ============================================================
@app.get("/debug/pdf-afip-path")
def debug_pdf_afip_path():
    import pdf_afip
    return {
        "real_file": getattr(pdf_afip, "__file__", "UNKNOWN"),
        "cwd": os.getcwd()
    }
