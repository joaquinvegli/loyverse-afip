import os
import subprocess
import tempfile
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def test_afip_connection():
    # ===============================
    # 1) Secret Files correctos
    # ===============================
    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        return {"error": f"No existe {key_path}"}

    if not os.path.exists(crt_path):
        return {"error": f"No existe {crt_path}"}

    # ===============================
    # 2) Generar CMS usando OpenSSL
    # ===============================
    try:
        cms_bytes = generar_cms(crt_path, key_path)
    except Exception as e:
        return {"error": f"Error generando CMS: {str(e)}"}

    # ===============================
    # 3) Llamar a WSAA.LoginCMS(cms)
    # ===============================
    wsaa = WSAA()
    wsaa.HOMO = False  # producción

    try:
        wsaa.LoginCMS(cms_bytes)
    except Exception as e:
        return {"error": f"Error en LoginCMS(): {str(e)}"}

    if wsaa.Excepcion:
        return {"error": f"WSAA error: {wsaa.Excepcion}"}

    # ===============================
    # 4) Consumir WSFE
    # ===============================
    wsfe = WSFEv1()
    wsfe.HOMO = False
    wsfe.Token = wsaa.Token
    wsfe.Sign = wsaa.Sign

    cuit = os.environ.get("AFIP_CUIT")
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))
    tipo_cbte = 11  # Factura C

    if not cuit:
        return {"error": "Falta AFIP_CUIT"}

    wsfe.Cuit = int(cuit)

    try:
        wsfe.CompUltimoAutorizado(tipo_cbte, pto_vta)
    except Exception as e:
        return {"error": f"WSFE error: {str(e)}"}

    if wsfe.Excepcion:
        return {"error": wsfe.Excepcion}

    return {
        "status": "ok",
        "ultimo_cbte": wsfe.CbteNro,
        "token": wsaa.Token[:25] + "...",
        "sign": wsaa.Sign[:25] + "..."
    }


def generar_cms(crt_path, key_path):
    """
    Genera el CMS en formato DER usando OpenSSL.
    """

    with tempfile.TemporaryDirectory() as tmp:
        req_xml = os.path.join(tmp, "req.xml")
        cms_out = os.path.join(tmp, "req.cms")

        # Generar XML base
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

        with open(req_xml, "w", encoding="utf-8") as f:
            f.write(xml_data)

        # Ejecutar OpenSSL
        cmd = [
            "openssl", "smime",
            "-sign",
            "-binary",
            "-signer", crt_path,
            "-inkey", key_path,
            "-in", req_xml,
            "-out", cms_out,
            "-outform", "DER",
            "-nodetach"
        ]

        res = subprocess.run(cmd, capture_output=True)

        if res.returncode != 0:
            raise Exception(res.stderr.decode(errors="ignore"))

        with open(cms_out, "rb") as f:
            return f.read()
