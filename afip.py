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
# 4) WSFE – FECAESolicitar (FACTURAR)
# ======================================================
def wsfe_facturar(tipo_cbte: int, doc_tipo: int, doc_nro: int, items: list, total: float):

    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        raise Exception("No existe clave privada AFIP")
    if not os.path.exists(crt_path):
        raise Exception("No existe certificado AFIP")

    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        raise Exception("Falta AFIP_CUIT")
    cuit_int = int(cuit)

    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

    # =========================================================
    # 1) WSAA – usar TOKEN CACHEADO si está disponible
    # =========================================================
    token, sign = cargar_wsaa()

    if not token or not sign:
        cms_b64 = generar_cms_der_b64(crt_path, key_path)
        token, sign = login_cms_directo(cms_b64)
        guardar_wsaa(token, sign)

    # =========================================================
    # 2) Obtener último comprobante
    # =========================================================
    try:
        ultimo = wsfe_ultimo_comprobante(
            token=token,
            sign=sign,
            cuit=cuit_int,
            pto_vta=pto_vta,
            tipo_cbte=tipo_cbte
        )
    except:
        # TOKEN VENCIDO → RENOVAR
        cms_b64 = generar_cms_der_b64(crt_path, key_path)
        token, sign = login_cms_directo(cms_b64)
        guardar_wsaa(token, sign)

        ultimo = wsfe_ultimo_comprobante(
            token=token,
            sign=sign,
            cuit=cuit_int,
            pto_vta=pto_vta,
            tipo_cbte=tipo_cbte
        )

    cbte_nro = ultimo + 1

    # =========================================================
    # 3) XML Items
    # =========================================================
    xml_items = ""
    for it in items:
        descripcion = it["descripcion"]
        cantidad = it["cantidad"]
        precio = it["precio"]
        importe_item = round(float(cantidad) * float(precio), 2)

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

    # =========================================================
    # 4) FECAESolicitar
    # =========================================================
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
            <ar:FchServDesde></ar:FchServDesde>
            <ar:FchServHasta></ar:FchServHasta>
            <ar:FchVtoPago></ar:FchVtoPago>
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

    for elem in tree.iter():
        if elem.tag.endswith("CAE"):
            cae = elem.text
        if elem.tag.endswith("CAEFchVto"):
            vto = elem.text

    if not cae:
        raise Exception("La AFIP no devolvió CAE. Error en la factura.")

    return {
        "cae": cae,
        "vencimiento": vto,
        "cbte_nro": cbte_nro,
        "pto_vta": pto_vta
    }
