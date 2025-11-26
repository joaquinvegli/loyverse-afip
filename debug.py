import os
from fastapi import APIRouter

router = APIRouter()

@router.get("/debug/key")
def debug_key():
    path = "/etc/secrets/afip_new.key"
    if not os.path.exists(path):
        return {"error": "NO EXISTE afip_new.key en secrets"}

    with open(path, "rb") as f:
        data = f.read()

    return {
        "len": len(data),
        "first_32_bytes": list(data[:32]),
        "as_text_preview": data[:80].decode(errors="replace")
    }

@router.get("/debug/crt")
def debug_crt():
    path = "/etc/secrets/afip_new.crt"
    if not os.path.exists(path):
        return {"error": "NO EXISTE afip_new.crt en secrets"}

    with open(path, "rb") as f:
        data = f.read()

    return {
        "len": len(data),
        "first_32_bytes": list(data[:32]),
        "as_text_preview": data[:80].decode(errors="replace")
    }
