import os
import subprocess
import tempfile
import base64
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def test_afip_connection():
    """
    Prueba WSAA + WSFE en producción usando Secret Files reales.
    """

    # ===========================
    # 1. CARGA DE ARCHIVOS
    # ===========================
    key_path = "/etc/secrets/afip.key"
    crt_path = "/etc/secrets/afip.crt"

    if not os.path.exists(key_path):
        return {"error": "NO existe el archivo secreto afip.key"}

    if not os.path.exists(crt_path):
        return {"error": "NO existe el archivo secreto afip.crt"}

    # Leer archivos tal cual
    with open(key_path, "rb") as f:
        private_key = f.read()

    with open(crt_path, "rb") as f:
        certificate = f.read()

    cuit = os.environ.get("AFIP_CUIT")
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

    if not cuit:
        return {"error": "Variable AFIP_CUIT no definida"}

    # ===========================
    # 2. GENERAR CMS (DER)
    # ===========================
    cms_der = generar_cms_bytes(private_key, certificate)

    # WSAA espera BASE64, NO DER
    cms_b64 = base64.b64encode(cms_der).decode()

    # ===========================
    # 3. WSAA (LOGIN)
    # ===========================
    wsaa = WSAA()
    wsaa.HOMO = False  # SIEMPRE producción

    ta = wsaa.LoginCMS(cms_b64)

    if wsaa.Excepcion:
        raise Exception("WSAA Error: " + wsaa.Excepcion)

    # ===========================
    # 4. WSFE
    # ===========================
    wsfe = WSFEv1()
    wsfe.Cuit = int(cuit)
    wsfe.Sign = wsaa.Sign
    wsfe.Token = wsaa.Token
    wsfe.HOMO = False  # producción

    tipo_cbte = 11  # Factura C
    wsfe.CompUltimoAutorizado(tipo_cbte, pto_vta)

    if wsfe.ErrMsg:
        raise Exception("WSFE Error: " + wsfe.ErrMsg)

    return {
        "status": "ok",
        "ultimo": wsfe.CbteNro,
        "token": wsaa.Token[:20] + "...",
        "sign": wsaa.Sign[:20] + "..."
    }


def generar_cms_bytes(private_key_bytes, certificate_bytes, service="wsfe"):
    """
    Genera un CMS válido (DER binario) usando openssl.
    """

    with tempfile.TemporaryDirectory() as tmp:
        key_path = os.path.join(tmp, "afip.key")
        crt_path = os.path.join(tmp, "afip.crt")
        xml_in = os.path.join(tmp, "req.xml")
        cms_out = os.path.join(tmp, "req.cms")

        # Guardar exactamente como binario
        with open(key_path, "wb") as f:
            f.write(private_key_bytes)

        with open(crt_path, "wb") as f:
            f.write(certificate_bytes)

        # XML para AFIP
        login_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>1</uniqueId>
    <generationTime>2024-01-01T00:00:00-03:00</generationTime>
    <expirationTime>2030-01-01T00:00:00-03:00</expirationTime>
  </header>
  <service>{service}</service>
</loginTicketRequest>
"""

        with open(xml_in, "w", encoding="utf-8") as f:
            f.write(login_xml)

        # Comando openssl
        cmd = [
            "openssl", "smime",
            "-sign",
            "-binary",
            "-signer", crt_path,
            "-inkey", key_path,
            "-in", xml_in,
            "-out", cms_out,
            "-outform", "DER",
            "-nodetach"
        ]

        res = subprocess.run(cmd, capture_output=True)

        if res.returncode != 0:
            raise Exception("Error creando CMS: " + res.stderr.decode(errors="ignore"))

        with open(cms_out, "rb") as f:
            return f.read()
