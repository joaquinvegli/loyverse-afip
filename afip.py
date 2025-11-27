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
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")  # FIX CRÍTICO
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
    """ Genera LoginTicketRequest firmado (CMS DER → BASE64). """

    TZ = timezone(timedelta(hours=-3))  # AFIP UTC-3
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
# 2) WSAA — LOGIN CMS
# ======================================================
def login_cms_directo(cms_b64: str):
    """
    Envía LoginCMS por SOAP y devuelve (token, sign).
    FIX IMPORTANTE: limpieza del XML escapado para evitar "loginCmsReturn vacío".
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

    # ----------------------------------------------------
    # Encontrar nodo <loginCmsReturn>
    # ----------------------------------------------------
    nodo_return = None
    for elem in tree.iter():
        if elem.tag.endswith("loginCmsReturn"):
            nodo_return = elem
            break

    if nodo_return is None:
        raise Exception("No se encontró nodo loginCmsReturn (WSAA respuesta inesperada)")

    raw_xml = nodo_return.text
    if not raw_xml:
        raise Exception("loginCmsReturn vacío (AFIP devolvió XML sin ticket)")

    # ----------------------------------------------------
    # FIX — desescapar XML
    # ----------------------------------------------------
    raw_xml = html.unescape(raw_xml).strip()

    # eliminar encabezado "<?xml ... ?>" si existe
    if raw_xml.startswith("<?xml"):
        raw_xml = raw_xml[raw_xml.find("?>") + 2:].strip()

    # ----------------------------------------------------
    # Parsear XML interno
    # ----------------------------------------------------
    inner = ET.fromstring(raw_xml)

    token, sign = None, None

    for elem in inner.iter():
        if elem.tag.endswith("token"):
            token = elem.text
        if elem.tag.endswith("sign"):
            sign = elem.text

    if not token or not sign:
        raise Exception("No se pudo extraer Token/Sign del XML parseado")

    return token, sign


# ======================================================
# 3) WSFE — FECompUltimoAutorizado
# ======================================================
def wsfe_ultimo_comprobante(token: str, sign: str, cuit: int, pto_vta: int, tipo_cbte: int):
    """ Obtiene el último comprobante autorizado. """

    from xml.etree import ElementTree as ET

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

    r = session.post(wsfe_url, data=soap_body.encode(), headers=headers, timeout=20)

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
# 4) WSFE — FACTURAR (FECAESolicitar)
# ======================================================
def wsfe_facturar(tipo_cbte: int, doc_tipo: int, doc_nro: int, items: list, total: float):
    """
    Factura REAL (Factura C)
    """

    import html
    from xml.etree import ElementTree as ET

    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        raise Exception("No existe afip_new.key")
    if not os.path.exists(crt_path):
        raise Exception("No existe afip_new.crt")

    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        raise Exception("Falta variable AFIP_CUIT")

    cuit_int = int(cuit)
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))
    wsfe_url = os.environ.get("AFIP_WSFE_URL", "https://servicios1.afip.gov.ar/wsfev1/service.asmx")

    # WSAA
    cms_b64 = generar_cms_der_b64(crt_path, key_path)
    token, sign = login_cms_directo(cms_b64)

    # Conseguir siguiente número
    ultimo = wsfe_ultimo_comprobante(token, sign, cuit_int, pto_vta, tipo_cbte)
    cbte_nro = ultimo + 1

    today = datetime.now().strftime("%Y%m%d")

    # Si no hay DNI → Consumidor Final (99)
    if not doc_nro:
        doc_tipo = 99
        doc_nro = 0

    # Ítems XML
    xml_items = ""
    for it in items:
        cant = it["cantidad"]
        precio = it["precio"]
        desc = it["descripcion"]
        total_item = round(float(cant) * float(precio), 2)

        xml_items += f"""
        <ar:Item>
          <ar:Pro_cod>{desc}</ar:Pro_cod>
          <ar:Pro_ds>{desc}</ar:Pro_ds>
          <ar:Pro_qty>{cant}</ar:Pro_qty>
          <ar:Pro_umed>7</ar:Pro_umed>
          <ar:Pro_precio>{precio}</ar:Pro_precio>
          <ar:Pro_total_item>{total_item}</ar:Pro_total_item>
        </ar:Item>
        """

    # SOAP
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
            <ar:CbteFch>{today}</ar:CbteFch>

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

    r = session.post(wsfe_url, data=soap_body.encode(), headers=headers, timeout=25)

    if r.status_code != 200:
        raise Exception(f"WSFE devolvió {r.status_code}: {r.text}")

    tree = ET.fromstring(r.text)

    cae = None
    venc = None

    for elem in tree.iter():
        if elem.tag.endswith("CAE"):
            cae = elem.text
        if elem.tag.endswith("CAEFchVto"):
            venc = elem.text

    if not cae:
        raise Exception("AFIP no devolvió CAE")

    return {
        "cbte_nro": cbte_nro,
        "cae": cae,
        "vencimiento": venc
    }


# ======================================================
# 5) TEST AFIP
# ======================================================
def test_afip_connection():
    """ WSAA + WSFE Ultimo comprobante """

    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        return {"error": f"No existe {key_path}"}
    if not os.path.exists(crt_path):
        return {"error": f"No existe {crt_path}"}

    cms_b64 = generar_cms_der_b64(crt_path, key_path)
    token, sign = login_cms_directo(cms_b64)

    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        return {"error": "Falta AFIP_CUIT"}

    cuit_int = int(cuit)
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))
    tipo_cbte = 11  # Factura C

    ultimo = wsfe_ultimo_comprobante(token, sign, cuit_int, pto_vta, tipo_cbte)

    return {
        "status": "ok",
        "ultimo_comprobante": ultimo,
        "token_inicio": token[:50] + "...",
        "sign_inicio": sign[:50] + "...",
        "detail": "WSAA OK + WSFE OK"
    }
