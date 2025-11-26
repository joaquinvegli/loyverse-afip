import os
import subprocess
import tempfile
import base64
import requests
from datetime import datetime, timedelta, timezone


# ======================================================
# 1) GENERAR CMS DER → BASE64  (como /debug/login_raw)
# ======================================================
def generar_cms_der_b64(crt_path: str, key_path: str) -> str:
    """
    Genera un LoginTicketRequest firmado en formato CMS DER (binario)
    y lo devuelve como base64, que es lo que AFIP espera.
    """

    # Zona horaria correcta para AFIP (UTC-3)
    TZ = timezone(timedelta(hours=-3))
    now = datetime.now(TZ)

    gen = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S%z")
    exp = (now + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S%z")

    # AFIP quiere -03:00 en lugar de -0300
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

    return base64.b64encode(cms_bytes).decode()


# ======================================================
# 2) LOGINCMS DIRECTO (WSAA) – PARSEA TOKEN Y SIGN
# ======================================================
def login_cms_directo(cms_b64: str):
    """
    LoginCMS por requests directamente (WSAA).
    Extrae Token & Sign desde el XML interno escapado que devuelve AFIP.
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

    # Parse SOAP
    tree = ET.fromstring(r.text)

    # Buscar nodo loginCmsReturn (donde AFIP mete el XML escapado)
    nodo_return = None
    for elem in tree.iter():
        if elem.tag.endswith("loginCmsReturn"):
            nodo_return = elem
            break

    if nodo_return is None:
        raise Exception("No se encontró loginCmsReturn en la respuesta")

    raw_xml = nodo_return.text
    if not raw_xml:
        raise Exception("loginCmsReturn está vacío")

    # AFIP devuelve XML escapado (&lt;...&gt;)
    raw_xml = html.unescape(raw_xml)

    inner = ET.fromstring(raw_xml)

    token, sign = None, None

    for elem in inner.iter():
        if elem.tag.endswith("token"):
            token = elem.text
        if elem.tag.endswith("sign"):
            sign = elem.text

    if not token or not sign:
        raise Exception("No se pudo extraer Token/Sign del XML interno")

    return token, sign


# ======================================================
# 3) WSFE – FECompUltimoAutorizado DIRECTO CON SOAP
# ======================================================
def wsfe_ultimo_comprobante(token: str, sign: str, cuit: int, pto_vta: int, tipo_cbte: int):
    """
    Llama a FECompUltimoAutorizado del WSFEv1 directamente con SOAP.
    Devuelve el número de último comprobante autorizado.
    """
    from xml.etree import ElementTree as ET

    # Podés cambiar a homologación seteando AFIP_WSFE_URL si alguna vez lo necesitás
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

    r = requests.post(wsfe_url, data=soap_body.encode("utf-8"), headers=headers, timeout=20)

    if r.status_code != 200:
        raise Exception(f"WSFEv1 devolvió {r.status_code}: {r.text}")

    tree = ET.fromstring(r.text)

    # Buscar CbteNro en la respuesta
    cbte_nro = None
    for elem in tree.iter():
        if elem.tag.endswith("CbteNro"):
            try:
                cbte_nro = int(elem.text)
            except (TypeError, ValueError):
                cbte_nro = None
            break

    # Si hay errores, intento devolver el mensaje de AFIP
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
            raise Exception("WSFEv1 errores: " + " | ".join(errores))
        else:
            raise Exception("No se pudo obtener CbteNro de la respuesta de WSFEv1")

    return cbte_nro


# ======================================================
# 4) FUNCIÓN QUE USA TODO LO ANTERIOR – /test/afip
# ======================================================
def test_afip_connection():
    """
    1) Genera CMS DER+Base64 con TZ correcto
    2) LoginCMS directo (WSAA)
    3) WSFEv1 FECompUltimoAutorizado con SOAP directo
    """

    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        return {"error": f"No existe {key_path}"}
    if not os.path.exists(crt_path):
        return {"error": f"No existe {crt_path}"}

    # 1) CMS DER+BASE64 (igual al que ya probaste en /debug/login_raw)
    try:
        cms_b64 = generar_cms_der_b64(crt_path, key_path)
    except Exception as e:
        return {"error": f"Error generando CMS: {e}"}

    # 2) LoginCMS directo a AFIP (WSAA)
    try:
        token, sign = login_cms_directo(cms_b64)
    except Exception as e:
        return {"error": f"Error en LoginCMS directo: {e}"}

    # 3) WSFE – FECompUltimoAutorizado
    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        return {"error": "Falta AFIP_CUIT en variables de entorno"}

    try:
        cuit_int = int(cuit)
    except:
        return {"error": f"AFIP_CUIT inválido: {cuit}"}

    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))
    tipo_cbte = int(os.environ.get("AFIP_TIPO_CBTE", "11"))  # 11 = Factura C por defecto

    try:
        ultimo_cbte = wsfe_ultimo_comprobante(token, sign, cuit_int, pto_vta, tipo_cbte)
    except Exception as e:
        return {"error": f"WSFE error: {e}"}

    return {
        "status": "ok",
        "ultimo_cbte": ultimo_cbte,
        "token_start": token[:40] + "...",
        "sign_start": sign[:40] + "...",
        "detail": "LoginCMS directo + WSFEv1 FECompUltimoAutorizado OK"
    }
