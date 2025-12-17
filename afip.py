import os
import subprocess
import tempfile
import base64
import requests
import ssl
import json
from datetime import datetime, timedelta, timezone
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.poolmanager import PoolManager
from xml.etree import ElementTree as ET

# ======================================================
# CACHE WSAA (token/sign temporales)
# ======================================================
WSAA_CACHE = "/tmp/wsaa_token.json"


def guardar_wsaa(token, sign):
    try:
        with open(WSAA_CACHE, "w") as f:
            json.dump({"token": token, "sign": sign}, f)
    except:
        pass


def cargar_wsaa():
    if not os.path.exists(WSAA_CACHE):
        return None, None
    try:
        with open(WSAA_CACHE, "r") as f:
            data = json.load(f)
            return data.get("token"), data.get("sign")
    except:
        return None, None


# ======================================================
# ADAPTADOR TLS (soluciona SSL: DH_KEY_TOO_SMALL)
# ======================================================
class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=ctx
        )


# ======================================================
# HELPERS DOC
# ======================================================
def doc_tipo_y_nro(cliente: dict | None):
    """
    Para Factura/NC C:
    - DNI => DocTipo 96
    - CUIT => DocTipo 80
    - Consumidor final sin dato => DocTipo 99 / DocNro 0
    """
    if not cliente:
        return 99, 0

    dni = (cliente.get("dni") or "").strip()
    cuit = (cliente.get("cuit") or "").strip()

    if cuit:
        solo = "".join(c for c in cuit if c.isdigit())
        if solo:
            return 80, int(solo)

    if dni:
        solo = "".join(c for c in dni if c.isdigit())
        if solo:
            return 96, int(solo)

    return 99, 0


# ======================================================
# 1) GENERAR CMS DER → BASE64
# ======================================================
def generar_cms_der_b64(crt_path: str, key_path: str) -> str:
    TZ = timezone(timedelta(hours=-3))
    now = datetime.now(TZ)

    gen = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S%z")
    exp = (now + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S%z")

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
# 2) LOGIN CMS (WSAA)
# ======================================================
def login_cms_directo(cms_b64: str):
    import html

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

    token = None
    sign = None

    for elem in inner.iter():
        if elem.tag.endswith("token"):
            token = elem.text
        if elem.tag.endswith("sign"):
            sign = elem.text

    if not token or not sign:
        raise Exception("No se pudo extraer token/sign del WSAA")

    return token, sign


# ======================================================
# 3) WSFE – FECompUltimoAutorizado
# ======================================================
def wsfe_ultimo_comprobante(token: str, sign: str, cuit: int, pto_vta: int, tipo_cbte: int):
    wsfe_url = os.environ.get(
        "AFIP_WSFE_URL",
        "https://servicios1.afip.gov.ar/wsfev1/service.asmx"
    )

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

    if cbte_nro is None:
        raise Exception("WSFE no devolvió número de comprobante")

    return cbte_nro


# ======================================================
# AUTH (token/sign) con cache y refresh automático
# ======================================================
def obtener_auth_wsaa():
    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        raise Exception("No existe clave privada AFIP")
    if not os.path.exists(crt_path):
        raise Exception("No existe certificado AFIP")

    token, sign = cargar_wsaa()
    if token and sign:
        return token, sign

    cms_b64 = generar_cms_der_b64(crt_path, key_path)
    token, sign = login_cms_directo(cms_b64)
    guardar_wsaa(token, sign)
    return token, sign


# ======================================================
# 4) WSFE – FECAESolicitar (FACTURAR)
# ======================================================
def wsfe_facturar(tipo_cbte: int, cliente: dict | None, items: list, total: float):

    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        raise Exception("Falta AFIP_CUIT")
    cuit_int = int(cuit)

    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

    doc_tipo, doc_nro = doc_tipo_y_nro(cliente)

    # Auth
    token, sign = obtener_auth_wsaa()

    # Último comprobante (refresh si token venció)
    try:
        ultimo = wsfe_ultimo_comprobante(token, sign, cuit_int, pto_vta, tipo_cbte)
    except:
        cms_b64 = generar_cms_der_b64("/etc/secrets/afip_new.crt", "/etc/secrets/afip_new.key")
        token, sign = login_cms_directo(cms_b64)
        guardar_wsaa(token, sign)
        ultimo = wsfe_ultimo_comprobante(token, sign, cuit_int, pto_vta, tipo_cbte)

    cbte_nro = ultimo + 1

    # Items XML
    xml_items = ""
    for it in items:
        descripcion = it["descripcion"]
        cantidad = float(it["cantidad"])
        precio = float(it["precio"])
        importe_item = round(cantidad * precio, 2)

        xml_items += f"""
        <ar:Item>
            <ar:Pro_cod>{descripcion}</ar:Pro_cod>
            <ar:Pro_ds>{descripcion}</ar:Pro_ds>
            <ar:Pro_qty>{cantidad}</ar:Pro_qty>
            <ar:Pro_umed>7</ar:Pro_umed>
            <ar:Pro_precio>{precio}</ar:Pro_precio>
            <ar:Pro_total_item>{importe_item}</ar:Pro_total_item>
        </ar:Item>
        """

    wsfe_url = os.environ.get(
        "AFIP_WSFE_URL",
        "https://servicios1.afip.gov.ar/wsfev1/service.asmx"
    )

    soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soapenv:Header/>
  <soapenv:Body>
    <ar:FECAESolicitar>
      <ar:Auth>
        <ar:Token>{token}</ar:Token>
        <ar:Sign>{sign}</ar:Sign>
        <ar:Cuit>{cuit_int}</ar:Cuit>
      </ar:Auth>
      <ar:FeCAEReq>
        <ar:FeCabReq>
          <ar:CantReg>1</ar:CantReg>
          <ar:PtoVta>{pto_vta}</ar:PtoVta>
          <ar:CbteTipo>{tipo_cbte}</ar:CbteTipo>
        </ar:FeCabReq>
        <ar:FeDetReq>
          <ar:FECAEDetRequest>
            <ar:Concepto>1</ar:Concepto>
            <ar:DocTipo>{doc_tipo}</ar:DocTipo>
            <ar:DocNro>{doc_nro}</ar:DocNro>
            <ar:CbteDesde>{cbte_nro}</ar:CbteDesde>
            <ar:CbteHasta>{cbte_nro}</ar:CbteHasta>
            <ar:CbteFch>{datetime.now().strftime('%Y%m%d')}</ar:CbteFch>
            <ar:ImpTotal>{total}</ar:ImpTotal>
            <ar:ImpTotConc>0</ar:ImpTotConc>
            <ar:ImpNeto>{total}</ar:ImpNeto>
            <ar:ImpOpEx>0</ar:ImpOpEx>
            <ar:ImpIVA>0</ar:ImpIVA>
            <ar:ImpTrib>0</ar:ImpTrib>
            <ar:MonId>PES</ar:MonId>
            <ar:MonCotiz>1</ar:MonCotiz>
            <ar:Items>
              {xml_items}
            </ar:Items>
          </ar:FECAEDetRequest>
        </ar:FeDetReq>
      </ar:FeCAEReq>
    </ar:FECAESolicitar>
  </soapenv:Body>
</soapenv:Envelope>
"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "http://ar.gov.afip.dif.FEV1/FECAESolicitar",
    }

    session = requests.Session()
    session.mount("https://", TLSAdapter())
    r = session.post(wsfe_url, data=soap_body.encode("utf-8"), headers=headers, timeout=20)

    if r.status_code != 200:
        raise Exception(f"WSFE devolvió {r.status_code}: {r.text}")

    tree = ET.fromstring(r.text)

    cae = None
    vto = None
    errores = []
    obs = []

    for elem in tree.iter():
        if elem.tag.endswith("CAE"):
            cae = elem.text
        if elem.tag.endswith("CAEFchVto"):
            vto = elem.text
        if elem.tag.endswith("ErrMsg"):
            errores.append(elem.text)

    errores = [str(e) for e in errores if e]
    obs = [str(o) for o in obs if o]

    if not cae:
        msg = "La AFIP rechazó la factura.\n"
        if errores:
            msg += "Errores: " + " | ".join(errores) + "\n"
        msg += "\nRespuesta completa AFIP:\n" + r.text[:2000]
        raise Exception(msg)

    return {
        "cae": cae,
        "vencimiento": vto,
        "cbte_nro": cbte_nro,
        "pto_vta": pto_vta
    }


# ======================================================
# 5) WSFE – NOTA DE CRÉDITO C (CbteTipo=13)
#    Asociada a Factura C (CbteTipo=11)
# ======================================================
def wsfe_nota_credito_c(cliente: dict | None,
                        items: list,
                        total: float,
                        factura_asociada: dict):
    """
    factura_asociada requiere:
    - cbte_nro
    - pto_vta
    (asumimos Factura C = tipo 11)
    """

    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        raise Exception("Falta AFIP_CUIT")
    cuit_int = int(cuit)

    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

    # Tipos AFIP
    TIPO_FACTURA_C = 11
    TIPO_NC_C = 13

    doc_tipo, doc_nro = doc_tipo_y_nro(cliente)

    # Auth
    token, sign = obtener_auth_wsaa()

    # Último NC
    try:
        ultimo = wsfe_ultimo_comprobante(token, sign, cuit_int, pto_vta, TIPO_NC_C)
    except:
        cms_b64 = generar_cms_der_b64("/etc/secrets/afip_new.crt", "/etc/secrets/afip_new.key")
        token, sign = login_cms_directo(cms_b64)
        guardar_wsaa(token, sign)
        ultimo = wsfe_ultimo_comprobante(token, sign, cuit_int, pto_vta, TIPO_NC_C)

    cbte_nro = ultimo + 1

    # Items XML
    xml_items = ""
    for it in items:
        descripcion = it["descripcion"]
        cantidad = float(it["cantidad"])
        precio = float(it["precio"])
        importe_item = round(cantidad * precio, 2)

        xml_items += f"""
        <ar:Item>
            <ar:Pro_cod>{descripcion}</ar:Pro_cod>
            <ar:Pro_ds>{descripcion}</ar:Pro_ds>
            <ar:Pro_qty>{cantidad}</ar:Pro_qty>
            <ar:Pro_umed>7</ar:Pro_umed>
            <ar:Pro_precio>{precio}</ar:Pro_precio>
            <ar:Pro_total_item>{importe_item}</ar:Pro_total_item>
        </ar:Item>
        """

    wsfe_url = os.environ.get(
        "AFIP_WSFE_URL",
        "https://servicios1.afip.gov.ar/wsfev1/service.asmx"
    )

    # CbtesAsoc: referenciar la Factura C original
    asoc_pto = int(factura_asociada["pto_vta"])
    asoc_nro = int(factura_asociada["cbte_nro"])

    soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soapenv:Header/>
  <soapenv:Body>
    <ar:FECAESolicitar>
      <ar:Auth>
        <ar:Token>{token}</ar:Token>
        <ar:Sign>{sign}</ar:Sign>
        <ar:Cuit>{cuit_int}</ar:Cuit>
      </ar:Auth>
      <ar:FeCAEReq>
        <ar:FeCabReq>
          <ar:CantReg>1</ar:CantReg>
          <ar:PtoVta>{pto_vta}</ar:PtoVta>
          <ar:CbteTipo>{TIPO_NC_C}</ar:CbteTipo>
        </ar:FeCabReq>
        <ar:FeDetReq>
          <ar:FECAEDetRequest>
            <ar:Concepto>1</ar:Concepto>
            <ar:DocTipo>{doc_tipo}</ar:DocTipo>
            <ar:DocNro>{doc_nro}</ar:DocNro>
            <ar:CbteDesde>{cbte_nro}</ar:CbteDesde>
            <ar:CbteHasta>{cbte_nro}</ar:CbteHasta>
            <ar:CbteFch>{datetime.now().strftime('%Y%m%d')}</ar:CbteFch>

            <ar:ImpTotal>{total}</ar:ImpTotal>
            <ar:ImpTotConc>0</ar:ImpTotConc>
            <ar:ImpNeto>{total}</ar:ImpNeto>
            <ar:ImpOpEx>0</ar:ImpOpEx>
            <ar:ImpIVA>0</ar:ImpIVA>
            <ar:ImpTrib>0</ar:ImpTrib>

            <ar:MonId>PES</ar:MonId>
            <ar:MonCotiz>1</ar:MonCotiz>

            <ar:CbtesAsoc>
              <ar:CbteAsoc>
                <ar:Tipo>{TIPO_FACTURA_C}</ar:Tipo>
                <ar:PtoVta>{asoc_pto}</ar:PtoVta>
                <ar:Nro>{asoc_nro}</ar:Nro>
              </ar:CbteAsoc>
            </ar:CbtesAsoc>

            <ar:Items>
              {xml_items}
            </ar:Items>
          </ar:FECAEDetRequest>
        </ar:FeDetReq>
      </ar:FeCAEReq>
    </ar:FECAESolicitar>
  </soapenv:Body>
</soapenv:Envelope>
"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "http://ar.gov.afip.dif.FEV1/FECAESolicitar",
    }

    session = requests.Session()
    session.mount("https://", TLSAdapter())
    r = session.post(wsfe_url, data=soap_body.encode("utf-8"), headers=headers, timeout=20)

    if r.status_code != 200:
        raise Exception(f"WSFE devolvió {r.status_code}: {r.text}")

    tree = ET.fromstring(r.text)

    cae = None
    vto = None
    errores = []

    for elem in tree.iter():
        if elem.tag.endswith("CAE"):
            cae = elem.text
        if elem.tag.endswith("CAEFchVto"):
            vto = elem.text
        if elem.tag.endswith("ErrMsg"):
            errores.append(elem.text)

    errores = [str(e) for e in errores if e]

    if not cae:
        msg = "La AFIP rechazó la Nota de Crédito.\n"
        if errores:
            msg += "Errores: " + " | ".join(errores) + "\n"
        msg += "\nRespuesta completa AFIP:\n" + r.text[:2000]
        raise Exception(msg)

    return {
        "cae": cae,
        "vencimiento": vto,
        "cbte_nro": cbte_nro,
        "pto_vta": pto_vta,
        "tipo_cbte": 13,
        "asoc_cbte_tipo": 11,
        "asoc_pto_vta": asoc_pto,
        "asoc_cbte_nro": asoc_nro,
    }
