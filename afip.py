import os
import subprocess
import tempfile
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def test_afip_connection():
    """
    Prueba WSAA + WSFE en producción.
    """

    # =====================================
    # 1. OBTENER ARCHIVOS DESDE SECRET FILES
    # =====================================
    key_path = "/etc/secrets/afip.key"
    crt_path = "/etc/secrets/afip.crt"

    if not os.path.exists(key_path):
        return {"error": "Archivo secreto afip.key NO existe en Render"}

    if not os.path.exists(crt_path):
        return {"error": "Archivo secreto afip.crt NO existe en Render"}

    # Leer los archivos EXACTOS (no utf8)
    with open(key_path, "rb") as f:
        private_key = f.read()

    with open(crt_path, "rb") as f:
        certificate = f.read()

    cuit = os.environ.get("AFIP_CUIT")
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

    # =====================================
    # 2. GENERAR CMS EN FORMATO BINARIO
    # =====================================
    cms = generar_cms_bytes(private_key, certificate)

    # =====================================
    # 3. WSAA
    # =====================================
    wsaa = WSAA()
    wsaa.HOMO = False  # producción

    ta = wsaa.LoginCMS(cms)

    if wsaa.Excepcion:
        raise Exception(wsaa.Excepcion)

    # =====================================
    # 4. WSFE
    # =====================================
    wsfe = WSFEv1()
    wsfe.Cuit = int(cuit)
    wsfe.Sign = wsaa.Sign
    wsfe.Token = wsaa.Token
    wsfe.HOMO = False

    tipo_cbte = 11  # Factura C
    wsfe.CompUltimoAutorizado(tipo_cbte, pto_vta)

    return {
        "status": "ok",
        "ultimo": wsfe.CbteNro,
        "token": wsaa.Token[:25] + "...",
        "sign": wsaa.Sign[:25] + "..."
    }


def generar_cms_bytes(private_key_bytes, certificate_bytes, service="wsfe"):
    """
    Genera CMS firmado — usando archivos binarios reales.
    """

    with tempfile.TemporaryDirectory() as tmp:
        key_path = os.path.join(tmp, "afip.key")
        crt_path = os.path.join(tmp, "afip.crt")
        xml_in = os.path.join(tmp, "req.xml")
        cms_out = os.path.join(tmp, "req.cms")

        # Guardar los archivos EXACTOS
        with open(key_path, "wb") as f:
            f.write(private_key_bytes)

        with open(crt_path, "wb") as f:
            f.write(certificate_bytes)

        # Crear XML de requerimiento
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

        # Firmar CMS usando openssl
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
            err = res.stderr.decode(errors="ignore")
            raise Exception(f"Error creando CMS: {err}")

        with open(cms_out, "rb") as f:
            return f.read()
