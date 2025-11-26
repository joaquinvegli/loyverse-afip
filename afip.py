import os
import subprocess
import tempfile
import base64
import requests
import ssl
from datetime import datetime, timedelta, timezone
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.poolmanager import PoolManager


# ======================================================
# ADAPTADOR TLS (soluciona: SSL: DH_KEY_TOO_SMALL)
# ======================================================
class TLSAdapter(HTTPAdapter):
    """
    Permite conectarse a servidores AFIP que usan DH inseguro.
    Render/Ubuntu bloquea por defecto, así que bajamos SECLEVEL a 1.
    """
    def init_poolmanager(self, connections, maxsize, block=False):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")  # <--- FIX CRÍTICO PARA AFIP
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=ctx
        )


# ======================================================
# 1) GENERAR CMS DER → BASE64  (como /debug/login_raw)
# ======================================================
def generar_cms_der_b64(crt_path: str, key_path: str) -> str:
    """
    Genera un LoginTicketRequest firmado en formato CMS DER (binario)
    y lo convierte a base64 para LoginCMS.
    """

    TZ = timezone(timedelta(hours=-3))  # AFIP siempre UTC-3
    now = datetime.now(TZ)

    gen = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S%z")
    exp = (now + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S%z")

    # convertir -0300 → -03:00
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

        # Firmar CMS (DER)
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

    return base64.b64encode(cms_bytes).decode()


# ======================================================
# 2) LOGIN CMS DIRECTO (WSAA)
# ======================================================
def login_cms_directo(cms_b64: str):
    """
    LoginCMS por POST directo a AFIP.
    Extrae Token y Sign del XML escapado.
    """
    import html
    from xml.etree import ElementTree as ET

    soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <loginCms>
      <in0>{cms_b64}</in0>
    </loginCms>
  </soapenv:Body>
</soapenv:Envelope>
"""

    url = "https://wsaa.afip.gov.ar/ws/services/LoginCms"
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "",
    }

    r = requests.post(url, data=soap_body.encode("utf-8"), headers=headers, timeout=20)

    if r.status_code != 200:
        raise Exception(f"WSAA devolvió {r.status_code}: {r.text}")

    tree = ET.fromstring(r.text)

    nodo_return = None
    for elem in tree.iter():
        if elem.tag.endswith("loginCmsReturn"):
            nodo_return = elem
            break

    if nodo_return is None:
        raise Exception("No se encontró loginCmsReturn en la respuesta")

    raw_xml = nodo_return.text
    if not raw_xml:
        raise Exception("loginCmsReturn vacío")

    raw_xml = html.unescape(raw_xml)
    inner = ET.fromstring(raw_xml)

    token, sign = None, None

    for elem in inner.iter():
        if elem.tag.endswith("token"):
            token = elem.text
        if elem.tag.endswith("sign"):
            sign = elem.text

    if not token or not sign:
        raise Exception("No se pudo extraer Token/Sign")

    return token, sign


# ======================================================
# 3) WSFE – FECompUltimoAutorizado DIRECTO CON SOAP
# ======================================================
def wsfe_ultimo_comprobante(token: str, sign: str, cuit: int, pto_vta: int, tipo_cbte: int):
    """ Consulta WSFE para obtener el último comprobante autorizado. """

    from xml.etree import ElementTree as ET

    wsfe_url = os.environ.get("AFIP_WSFE_URL", "https://servicios1.afip.gov.ar/wsfev1/service.asmx")

    soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soapenv:Header/>
  <soapenv:Body>
    <ar:FECompUltimoAutorizado>
      <ar:Auth>
        <ar:Token>{token}</ar:Token>
        <ar:Sign>{sign}</ar:Sign>
        <ar:Cuit>{cuit}</ar:Cuit>
      </ar:Auth>
      <ar:PtoVta>{pto_vta}</ar:PtoVta>
      <ar:CbteTipo>{tipo_cbte}</ar:CbteTipo>
    </ar:FECompUltimoAutorizado>
  </soapenv:Body>
</soapenv:Envelope>
"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "http://ar.gov.afip.dif.FEV1/FECompUltimoAutorizado",
    }

    # Sesión con el adaptador TLS inseguro para AFIP
    session = requests.Session()
    session.mount("https://", TLSAdapter())

    r = session.post(wsfe_url, data=soap_body.encode("utf-8"), headers=headers, timeout=20)

    if r.status_code != 200:
        raise Exception(f"WSFE devolvió {r.status_code}: {r.text}")

    tree = ET.fromstring(r.text)

    cbte_nro = None
    for elem in tree.iter():
        if elem.tag.endswith("CbteNro"):
            try:
                cbte_nro = int(elem.text)
            except:
                cbte_nro = None
            break

    # errores de AFIP
    if cbte_nro is None:
        errores = []
        for elem in tree.iter():
            if elem.tag.endswith("Err"):
                code = None
                msg = None
                for child in elem:
                    if child.tag.endswith("Code"):
                        code = child.text
                    if child.tag.endswith("Msg"):
                        msg = child.text
                if code or msg:
                    errores.append(f"{code}: {msg}")
        if errores:
            raise Exception("WSFE errores: " + " | ".join(errores))
        else:
            raise Exception("No se pudo obtener CbteNro de WSFE")

    return cbte_nro


# ======================================================
# 4) PUNTO DE ENTRADA /test/afip
# ======================================================
def test_afip_connection():
    """ Conexión completa a AFIP: WSAA + WSFE """

    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        return {"error": f"No existe {key_path}"}
    if not os.path.exists(crt_path):
        return {"error": f"No existe {crt_path}"}

    # ------- WSAA -------
    try:
        cms_b64 = generar_cms_der_b64(crt_path, key_path)
        token, sign = login_cms_directo(cms_b64)
    except Exception as e:
        return {"error": f"Error WSAA: {e}"}

    # ------- WSFE -------
    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        return {"error": "Falta variable AFIP_CUIT"}

    try:
        cuit_int = int(cuit)
    except:
        return {"error": f"AFIP_CUIT inválido: {cuit}"}

    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))
    tipo_cbte = int(os.environ.get("AFIP_TIPO_CBTE", "11"))

    try:
        ultimo = wsfe_ultimo_comprobante(token, sign, cuit_int, pto_vta, tipo_cbte)
    except Exception as e:
        return {"error": f"WSFE error: {e}"}

    return {
        "status": "ok",
        "ultimo_comprobante": ultimo,
        "token_start": token[:50] + "...",
        "sign_start": sign[:50] + "...",
        "detail": "WSAA OK + WSFE OK"
    }
