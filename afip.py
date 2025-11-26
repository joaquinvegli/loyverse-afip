import os
import subprocess
import tempfile
import base64
from datetime import datetime, timedelta, timezone

from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def generar_cms_b64(crt_path: str, key_path: str) -> str:
    """
    Genera el LoginTicketRequest firmado en formato CMS (DER),
    lo convierte a base64 y lo devuelve como string listo para
    ser enviado a WSAA.LoginCMS().
    """
    TZ = timezone(timedelta(hours=-3))  # Argentina UTC-3
    now = datetime.now(TZ)

    gen = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S%z")
    exp = (now + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S%z")

    # pasar de -0300 a -03:00
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
            raise Exception("OpenSSL error: " + res.stderr.decode(errors="ignore"))

        with open(cms_der, "rb") as f:
            cms_bytes = f.read()

    cms_b64 = base64.b64encode(cms_bytes).decode()
    return cms_b64


def test_afip_connection():
    """
    1) Genera CMS base64 (igual que /debug/login_raw, pero sin SOAP).
    2) Llama a WSAA.LoginCMS() usando pyafipws.
    3) Usa el token/sign para consultar WSFE (último comprobante autorizado).
    """
    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        return {"error": f"No existe {key_path}"}
    if not os.path.exists(crt_path):
        return {"error": f"No existe {crt_path}"}

    # ==========================
    # 1) Generar CMS base64
    # ==========================
    try:
        cms_b64 = generar_cms_b64(crt_path, key_path)
    except Exception as e:
        return {"error": f"Error generando CMS: {e}"}

    # ==========================
    # 2) WSAA.LoginCMS
    # ==========================
    wsaa = WSAA()
    wsaa.HOMO = False  # Producción

    try:
        wsaa.LoginCMS(cms_b64)
    except Exception as e:
        return {"error": f"Error en LoginCMS(): {e}"}

    if wsaa.Excepcion:
        return {"error": f"WSAA error: {wsaa.Excepcion}"}

    # ==========================
    # 3) WSFE: último comprobante
    # ==========================
    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        return {"error": "Falta AFIP_CUIT en variables de entorno"}

    try:
        cuit_int = int(cuit)
    except ValueError:
        return {"error": f"AFIP_CUIT inválido: {cuit}"}

    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))
    tipo_cbte = 11  # Factura C (cambiable)

    wsfe = WSFEv1()
    wsfe.HOMO = False  # Producción
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
        "detail": "Autenticación WSAA y consulta WSFE OK",
    }
