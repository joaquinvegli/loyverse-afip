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

    from xml.etree import ElementTree as ET2
    if r.status_code != 200:
        raise Exception(f"WSFE devolvió {r.status_code}: {r.text}")

    tree = ET2.fromstring(r.text)

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
# 3b) WSFE – FECAESolicitar (FACTURAR) DIRECTO CON SOAP
# ======================================================
def wsfe_facturar(tipo_cbte: int, doc_tipo: int, doc_nro: int, items: list, total: float):
    """
    Genera una factura (por ahora Factura C) usando WSFE → FECAESolicitar.
    - Usa WSAA (generar_cms_der_b64 + login_cms_directo)
    - Usa wsfe_ultimo_comprobante para calcular el próximo número
    - Devuelve: cae, vencimiento, cbte_nro
    """

    from xml.etree import ElementTree as ET

    # ---------------------------
    # Paths certificados
    # ---------------------------
    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        raise Exception(f"No existe {key_path}")
    if not os.path.exists(crt_path):
        raise Exception(f"No existe {crt_path}")

    # ---------------------------
    # WSAA → Token / Sign
    # ---------------------------
    cms_b64 = generar_cms_der_b64(crt_path, key_path)
    token, sign = login_cms_directo(cms_b64)

    # ---------------------------
    # Datos básicos desde ENV
    # ---------------------------
    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        raise Exception("Falta variable AFIP_CUIT")

    try:
        cuit_int = int(cuit)
    except:
        raise Exception(f"AFIP_CUIT inválido: {cuit}")

    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))
    wsfe_url = os.environ.get("AFIP_WSFE_URL", "https://servicios1.afip.gov.ar/wsfev1/service.asmx")

    # ---------------------------
    # Obtener próximo número de comprobante
    # ---------------------------
    ultimo = wsfe_ultimo_comprobante(token, sign, cuit_int, pto_vta, tipo_cbte)
    cbte_nro = ultimo + 1

    # ---------------------------
    # Fechas e importes
    # ---------------------------
    today = datetime.now().strftime("%Y%m%d")  # AAAAMMDD

    imp_total = float(total)
    imp_tot_conc = 0.0
    imp_neto = float(total)    # En Factura C sin IVA, el total = neto
    imp_trib = 0.0
    imp_op_ex = 0.0
    imp_iva = 0.0

    # Concepto 1 = Productos
    concepto = 1

    # Si no hay doc_nro, usar 0 y doc_tipo 99 (Consumidor Final)
    if not doc_nro:
        doc_tipo = 99
        doc_nro = 0

    # ---------------------------
    # SOAP FECAESolicitar
    # ---------------------------
    # Armamos una sola línea de detalle, usando el total.
    soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
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
            <ar:Concepto>{concepto}</ar:Concepto>
            <ar:DocTipo>{doc_tipo}</ar:DocTipo>
            <ar:DocNro>{doc_nro}</ar:DocNro>
            <ar:CbteDesde>{cbte_nro}</ar:CbteDesde>
            <ar:CbteHasta>{cbte_nro}</ar:CbteHasta>
            <ar:CbteFch>{today}</ar:CbteFch>
            <ar:ImpTotal>{imp_total:.2f}</ar:ImpTotal>
            <ar:ImpTotConc>{imp_tot_conc:.2f}</ar:ImpTotConc>
            <ar:ImpNeto>{imp_neto:.2f}</ar:ImpNeto>
            <ar:ImpOpEx>{imp_op_ex:.2f}</ar:ImpOpEx>
            <ar:ImpIVA>{imp_iva:.2f}</ar:ImpIVA>
            <ar:ImpTrib>{imp_trib:.2f}</ar:ImpTrib>
            <ar:MonId>PES</ar:MonId>
            <ar:MonCotiz>1.00</ar:MonCotiz>
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
        raise Exception(f"WSFE FECAESolicitar devolvió {r.status_code}: {r.text}")

    tree = ET.fromstring(r.text)

    # ---------------------------
    # Buscar CAE y fecha de vencimiento
    # ---------------------------
    cae = None
    fch_vto = None
    for elem in tree.iter():
        if elem.tag.endswith("CAE"):
            cae = elem.text
        if elem.tag.endswith("CAEFchVto"):
            fch_vto = elem.text

    if not cae:
        # Intentar leer errores si no hay CAE
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
            raise Exception("WSFE FECAESolicitar errores: " + " | ".join(errores))
        else:
            raise Exception("No se obtuvo CAE en la respuesta de FECAESolicitar")

    return {
        "cae": cae,
        "vencimiento": fch_vto,
        "cbte_nro": cbte_nro,
        "tipo_cbte": tipo_cbte,
        "pto_vta": pto_vta,
    }


# ======================================================
# 4) PUNTO DE ENTRADA /test/afip
# ======================================================
def test_afip_connection():
    """ Conexión completa a AFIP: WSAA + WSFE (último comprobante). """

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
