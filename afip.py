import os
import subprocess
import tempfile
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def generar_cms(private_key, certificate, service="wsfe"):
    """
    Genera un CMS firmado usando openssl (AFIP lo requiere así).
    """

    with tempfile.TemporaryDirectory() as tmp:
        key_path = os.path.join(tmp, "afip.key")
        crt_path = os.path.join(tmp, "afip.crt")
        req_path = os.path.join(tmp, "login.xml")
        cms_path = os.path.join(tmp, "loginCMS.xml")

        # Guardar KEY y CERT
        with open(key_path, "w") as f:
            f.write(private_key)

        with open(crt_path, "w") as f:
            f.write(certificate)

        # Archivo de requerimiento
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

        with open(req_path, "w") as f:
            f.write(login_xml)

        # Firmar usando openssl
        cmd = [
            "openssl", "smime",
            "-sign",
            "-signer", crt_path,
            "-inkey", key_path,
            "-nodetach",
            "-outform", "DER",
            "-in", req_path,
            "-out", cms_path,
        ]

        res = subprocess.run(cmd, capture_output=True)

        if res.returncode != 0:
            raise Exception(f"Error generando CMS: {res.stderr.decode()}")

        with open(cms_path, "rb") as f:
            return f.read()


def test_afip_connection():
    """
    Solo prueba la conexión WSAA + WSFE.
    """

    key = os.environ.get("AFIP_CERT_KEY")
    cert = os.environ.get("AFIP_CERT_CRT")
    cuit = os.environ.get("AFIP_CUIT")
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

    if not key or not cert:
        return {"error": "Variables AFIP_CERT_KEY o AFIP_CERT_CRT no están definidas"}

    # =====================================
    # 1. Generar CMS firmado (AFIP requiere esto)
    # =====================================
    cms = generar_cms(key, cert)

    # =====================================
    # 2. Enviar CMS al WSAA
    # =====================================
    wsaa = WSAA()
    wsaa.HOMO = False  # PRODUCCIÓN

    ta_string = wsaa.LoginCMS(cms)

    if wsaa.Excepcion:
        raise Exception(wsaa.Excepcion)

    # =====================================
    # 3. Conectar WSFE
    # =====================================
    wsfe = WSFEv1()
    wsfe.Cuit = int(cuit)
    wsfe.Sign = wsaa.Sign
    wsfe.Token = wsaa.Token
    wsfe.HOMO = False  # PRODUCCIÓN

    # Pedimos último comprobante
    tipo_cbte = 11  # Factura C
    wsfe.CompUltimoAutorizado(tipo_cbte, pto_vta)

    return {
        "status": "ok",
        "ultimo": wsfe.CbteNro,
        "token": wsaa.Token[:20] + "...",
        "sign": wsaa.Sign[:20] + "..."
    }
