import os
import subprocess
import tempfile
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def test_afip_connection():
    """
    Prueba WSAA + WSFE usando archivos REALES en Render.
    """

    # =====================================
    # 1. ARCHIVOS SECRETOS
    # =====================================
    key_path = "/etc/secrets/afip.key"
    crt_path = "/etc/secrets/afip.crt"

    if not os.path.exists(key_path):
        return {"error": "No existe /etc/secrets/afip.key"}

    if not os.path.exists(crt_path):
        return {"error": "No existe /etc/secrets/afip.crt"}

    # Leemos EXACTO, en binario, sin interpretar
    with open(key_path, "rb") as f:
        private_key = f.read()

    with open(crt_path, "rb") as f:
        certificate = f.read()

    cuit = os.environ.get("AFIP_CUIT")
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

    if not cuit:
        return {"error": "Falta variable AFIP_CUIT"}

    # =====================================
    # 2. GENERAR CMS (OpenSSL DER)
    # =====================================
    try:
        cms = generar_cms_bytes(
            private_key_bytes=private_key,
            certificate_bytes=certificate,
            service="wsfe"
        )
    except Exception as e:
        return {"error": f"Error generando CMS: {str(e)}"}

    # =====================================
    # 3. WSAA: LoginCMS
    # =====================================
    wsaa = WSAA()
    wsaa.HOMO = False   # PRODUCCIÓN

    ta = wsaa.LoginCMS(cms)

    if wsaa.Excepcion:
        return {"error": f"WSAA: {wsaa.Excepcion}"}

    if not wsaa.Token or not wsaa.Sign:
        return {"error": "WSAA no devolvió token/sign"}

    # =====================================
    # 4. WSFE
    # =====================================
    wsfe = WSFEv1()
    wsfe.Cuit = int(cuit)
    wsfe.HOMO = False
    wsfe.Token = wsaa.Token
    wsfe.Sign = wsaa.Sign

    tipo_cbte = 11  # Factura C

    try:
        wsfe.CompUltimoAutorizado(tipo_cbte, pto_vta)
    except Exception as e:
        return {"error": f"WSFE error: {str(e)}"}

    if wsfe.ErrMsg:
        return {"error": f"AFIP devolvió error: {wsfe.ErrMsg}"}

    return {
        "status": "ok",
        "ultimo_cbte": wsfe.CbteNro,
        "pto_vta": pto_vta,
        "token": wsaa.Token[:30] + "...",
        "sign": wsaa.Sign[:30] + "..."
    }


def generar_cms_bytes(private_key_bytes, certificate_bytes, service="wsfe"):
    """
    Genera CMS para WSAA usando OpenSSL en formato DER.
    """
    with tempfile.TemporaryDirectory() as tmp:

        key_file = os.path.join(tmp, "afip.key")
        crt_file = os.path.join(tmp, "afip.crt")
        xml_file = os.path.join(tmp, "login.xml")
        cms_file = os.path.join(tmp, "login.cms")

        # Escribir archivos EXACTOS
        with open(key_file, "wb") as f:
            f.write(private_key_bytes)

        with open(crt_file, "wb") as f:
            f.write(certificate_bytes)

        # Crear XML con fechas amplias
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>123</uniqueId>
    <generationTime>2020-01-01T00:00:00-03:00</generationTime>
    <expirationTime>2030-01-01T00:00:00-03:00</expirationTime>
  </header>
  <service>{service}</service>
</loginTicketRequest>
"""

        with open(xml_file, "w", encoding="utf-8") as f:
            f.write(xml)

        # Ejecutar OpenSSL para firmar CMS (DER)
        cmd = [
            "openssl", "smime",
            "-sign",
            "-binary",
            "-signer", crt_file,
            "-inkey", key_file,
            "-in", xml_file,
            "-out", cms_file,
            "-outform", "DER",
            "-nodetach"
        ]

        result = subprocess.run(cmd, capture_output=True)

        if result.returncode != 0:
            err = result.stderr.decode(errors="ignore")
            raise Exception(f"OpenSSL error: {err}")

        # Leer CMS binario
        with open(cms_file, "rb") as f:
            return f.read()
