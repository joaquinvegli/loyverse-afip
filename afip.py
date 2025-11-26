import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def generar_cms_pem(crt_path: str, key_path: str) -> str:
    """
    Genera un CMS en formato PEM (PKCS7 Base64) que es el formato
    que PyAfipWS necesita recibir en LoginCMS().
    """

    # Argentina UTC-3
    TZ = timezone(timedelta(hours=-3))
    now = datetime.now(TZ)

    gen = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S%z")
    exp = (now + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S%z")

    # corregir zona horaria: -0300 → -03:00
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
        cms_pem = os.path.join(tmp, "req.pem")

        with open(req_xml, "w", encoding="utf-8") as f:
            f.write(xml_data)

        # CMS en formato PEM (requerido por PyAfipWS)
        cmd = [
            "openssl", "smime", "-sign",
            "-signer", crt_path,
            "-inkey", key_path,
            "-in", req_xml,
            "-out", cms_pem,
            "-outform", "PEM",
            "-nodetach"
        ]

        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0:
            raise Exception("OpenSSL error: " + res.stderr.decode(errors="ignore"))

        with open(cms_pem, "r", encoding="utf-8", errors="ignore") as f:
            pem_text = f.read()

    return pem_text


def test_afip_connection():
    """
    1) Genera CMS en formato PEM (PARA PyAfipWS).
    2) Llama a WSAA.LoginCMS().
    3) Usa Token & Sign en WSFE.
    """

    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        return {"error": f"No existe {key_path}"}
    if not os.path.exists(crt_path):
        return {"error": f"No existe {crt_path}"}

    # ==========================
    # 1) CMS formato PEM
    # ==========================
    try:
        cms_pem = generar_cms_pem(crt_path, key_path)
    except Exception as e:
        return {"error": f"Error generando CMS PEM: {e}"}

    # ==========================
    # 2) WSAA.LoginCMS
    # ==========================
    wsaa = WSAA()
    wsaa.HOMO = False  # PRODUCCIÓN

    try:
        wsaa.LoginCMS(cms_pem)
    except Exception as e:
        return {"error": f"Error en LoginCMS(): {e}"}

    if wsaa.Excepcion:
        return {"error": f"WSAA error: {wsaa.Excepcion}"}

    # ==========================
    # 3) WSFE: último comprobante
    # ==========================
    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        return {"error": "Falta AFIP_CUIT"}

    try:
        cuit_int = int(cuit)
    except:
        return {"error": f"AFIP_CUIT inválido: {cuit}"}

    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))
    tipo_cbte = 11  # Factura C

    wsfe = WSFEv1()
    wsfe.HOMO = False
    wsfe.Token = wsaa.Token
    wsfe.Sign = wsaa.Sign
    wsfe.Cuit = cuit_int

    try:
        wsfe.CompUltimoAutorizado(tipo_cbte, pto_vta)
    except Exception as e:
        return {"error": f"WSFE error: {e}"}

    if wsfe.Excepcion:
        return {"error": f"WSFE error: {wsfe.Excepcion}"}

    return {
        "status": "ok",
        "ultimo_cbte": wsfe.CbteNro,
        "token_start": wsaa.Token[:40] + "...",
        "sign_start": wsaa.Sign[:40] + "...",
        "detail": "Autenticación WSAA + WSFE OK"
    }
