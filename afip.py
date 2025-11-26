import os
import subprocess
import tempfile
import base64
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def test_afip_connection():
    """
    Prueba WSAA + WSFE usando key y cert reales desde Secret Files.
    """

    # =====================================
    # 1. ARCHIVOS REALES DESDE SECRET FILES
    # =====================================
    key_path = "/etc/secrets/afip.key"
    crt_path = "/etc/secrets/afip.crt"

    if not os.path.exists(key_path):
        return {"error": "Archivo secreto afip.key NO existe en Render"}

    if not os.path.exists(crt_path):
        return {"error": "Archivo secreto afip.crt NO existe en Render"}

    # Leer RAW (sin interpretar texto)
    with open(key_path, "rb") as f:
        private_key = f.read()

    with open(crt_path, "rb") as f:
        certificate = f.read()

    cuit = os.environ.get("AFIP_CUIT")
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

    if not cuit:
        return {"error": "Variable AFIP_CUIT no definida"}

    # =====================================
    # 2. CREAR CMS (binario DER)
    # =====================================
    try:
        cms_der = generar_cms_bytes(private_key, certificate)
    except Exception as e:
        return {"error": f"Error generando CMS: {str(e)}"}

    # =====================================
    # 3. WSAA — LoginCMS en producción
    # =====================================
    wsaa = WSAA()
    wsaa.HOMO = False  # siempre producción AFIP

    # Convertir DER → Base64 → UTF8 → string
    cms_b64 = base64.b64encode(cms_der).decode("ascii")

    try:
        ta = wsaa.loginCms(cms_b64)
    except Exception as e:
        return {"error": f"Error en loginCms(): {str(e)}"}

    if wsaa.Excepcion:
        return {"error": f"WSAA Excepcion: {wsaa.Excepcion}"}

    # =====================================
    # 4. WSFE — consultar último comprobante
    # =====================================
    wsfe = WSFEv1()
    wsfe.Cuit = int(cuit)
    wsfe.Sign = wsaa.Sign
    wsfe.Token = wsaa.Token
    wsfe.HOMO = False  # producción

    tipo_cbte = 11  # Factura C

    try:
        wsfe.CompUltimoAutorizado(tipo_cbte, pto_vta)
    except Exception as e:
        return {"error": f"Error en WSFE.CompUltimoAutorizado: {str(e)}"}

    if wsfe.ErrMsg:
        return {"error": f"WSFE devolvió error: {wsfe.ErrMsg}"}

    # =====================================
    # RESPUESTA OK
    # =====================================
    return {
        "status": "ok",
        "pto_vta": pto_vta,
        "ultimo_cbte": wsfe.CbteNro,
        "token_start": wsaa.Token[:40] + "...",
        "sign_start": wsaa.Sign[:40] + "..."
    }


def generar_cms_bytes(private_key_bytes, certificate_bytes, service="wsfe"):
    """
    Genera un CMS firmado (DER binario) para AFIP WSAA usando OpenSSL.
    """

    with tempfile.TemporaryDirectory() as tmp:
        key_file = os.path.join(tmp, "afip.key")
        crt_file = os.path.join(tmp, "afip.crt")
        xml_in = os.path.join(tmp, "req.xml")
        cms_out = os.path.join(tmp, "req.cms")

        # Guardar archivos EXACTOS
        with open(key_file, "wb") as f:
            f.write(private_key_bytes)

        with open(crt_file, "wb") as f:
            f.write(certificate_bytes)

        # XML del LoginTicketRequest
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

        # OpenSSL → firmar CMS
        cmd = [
            "openssl", "smime",
            "-sign",
            "-binary",
            "-signer", crt_file,
            "-inkey", key_file,
            "-in", xml_in,
            "-out", cms_out,
            "-outform", "DER",
            "-nodetach"
        ]

        res = subprocess.run(cmd, capture_output=True)

        if res.returncode != 0:
            err = res.stderr.decode(errors="ignore")
            raise Exception(f"openssl error: {err}")

        with open(cms_out, "rb") as f:
            return f.read()
