import os
import subprocess
import tempfile
import base64
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def test_afip_connection():

    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        return {"error": "NO existe afip_new.key en secrets"}

    if not os.path.exists(crt_path):
        return {"error": "NO existe afip_new.crt en secrets"}

    with open(key_path, "rb") as f:
        private_key = f.read()

    with open(crt_path, "rb") as f:
        certificate = f.read()

    cuit = os.environ.get("AFIP_CUIT")
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

    # ======================
    # GENERAR CMS BASE64
    # ======================
    cms_b64 = generar_cms_base64(private_key, certificate)

    # ======================
    # WSAA PRODUCCIÓN
    # ======================
    wsaa = WSAA()
    wsaa.HOMO = False

    ta = wsaa.LoginCMS(cms_b64)

    if wsaa.Excepcion:
        return {"error": f"Error LoginCMS(): {wsaa.Excepcion}"}

    # ======================
    # WSFE
    # ======================
    wsfe = WSFEv1()
    wsfe.Cuit = int(cuit)
    wsfe.Sign = wsaa.Sign
    wsfe.Token = wsaa.Token
    wsfe.HOMO = False

    tipo_cbte = 11
    wsfe.CompUltimoAutorizado(tipo_cbte, pto_vta)

    return {
        "status": "ok",
        "ultimo": wsfe.CbteNro,
        "token": wsaa.Token[:40] + "...",
        "sign": wsaa.Sign[:40] + "..."
    }


def generar_cms_base64(private_key_bytes, certificate_bytes, service="wsfe"):
    with tempfile.TemporaryDirectory() as tmp:
        key_path = os.path.join(tmp, "key.pem")
        crt_path = os.path.join(tmp, "crt.pem")
        xml_in = os.path.join(tmp, "req.xml")
        cms_out = os.path.join(tmp, "req.pem")

        # Guardar archivos tal cual
        with open(key_path, "wb") as f:
            f.write(private_key_bytes)

        with open(crt_path, "wb") as f:
            f.write(certificate_bytes)

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>1234</uniqueId>
    <generationTime>2023-01-01T00:00:00-03:00</generationTime>
    <expirationTime>2030-01-01T00:00:00-03:00</expirationTime>
  </header>
  <service>{service}</service>
</loginTicketRequest>
"""

        with open(xml_in, "w", encoding="utf-8") as f:
            f.write(xml)

        # IMPORTANTE: GENERAR EN PEM
        cmd = [
            "openssl", "smime",
            "-sign",
            "-signer", crt_path,
            "-inkey", key_path,
            "-in", xml_in,
            "-out", cms_out,
            "-outform", "PEM",
            "-nodetach"
        ]

        res = subprocess.run(cmd, capture_output=True)

        if res.returncode != 0:
            raise Exception("Error creando CMS: " + res.stderr.decode(errors="ignore"))

        # Leer PEM y EXTRAER SOLO EL BASE64
        with open(cms_out, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

        # limpiar encabezados
        lines = [l for l in text.splitlines() if "BEGIN" not in l and "END" not in l]
        base64_text = "".join(lines)

        return base64_text
