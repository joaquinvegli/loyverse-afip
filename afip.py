# ======================================================
# WSFE – GENERAR FACTURA C (versión única y corregida)
# ======================================================
def wsfe_facturar(tipo_cbte: int, doc_tipo: int, doc_nro: int, items: list, total: float):
    """
    Genera FACTURA C usando WSAA + WSFE (SOAP directo).
    Devuelve: cbte_nro, cae, vencimiento, tipo_cbte, pto_vta.
    """

    from xml.etree import ElementTree as ET

    # -------------------------------------------
    # Certificados y CUIT
    # -------------------------------------------
    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        raise Exception("No existe clave privada AFIP")
    if not os.path.exists(crt_path):
        raise Exception("No existe certificado AFIP")

    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        raise Exception("Falta variable AFIP_CUIT")

    cuit_int = int(cuit)
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

    wsfe_url = os.environ.get(
        "AFIP_WSFE_URL",
        "https://servicios1.afip.gov.ar/wsfev1/service.asmx"
    )

    # -------------------------------------------
    # 1) WSAA Login → Token y Sign
    # -------------------------------------------
    cms_b64 = generar_cms_der_b64(crt_path, key_path)
    token, sign = login_cms_directo(cms_b64)

    # -------------------------------------------
    # 2) WSFE → último comprobante
    # -------------------------------------------
    ultimo = wsfe_ultimo_comprobante(token, sign, cuit_int, pto_vta, tipo_cbte)
    cbte_nro = ultimo + 1

    # -------------------------------------------
    # Concepto e importes
    # -------------------------------------------
    fecha_cbte = datetime.now().strftime("%Y%m%d")

    imp_total = float(total)
    imp_neto = imp_total  # en Factura C el total es neto

    # -------------------------------------------
    # Armar XML de ítems
    # -------------------------------------------
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
        </ar:Item>"""

    # -------------------------------------------
    # SOAP FECAESolicitar
    # -------------------------------------------
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
            <ar:CbteFch>{fecha_cbte}</ar:CbteFch>
            <ar:ImpTotal>{imp_total}</ar:ImpTotal>
            <ar:ImpTotConc>0</ar:ImpTotConc>
            <ar:ImpNeto>{imp_neto}</ar:ImpNeto>
            <ar:ImpOpEx>0</ar:ImpOpEx>
            <ar:ImpIVA>0</ar:ImpIVA>
            <ar:ImpTrib>0</ar:ImpTrib>
            <ar:MonId>PES</ar:MonId>
            <ar:MonCotiz>1.00</ar:MonCotiz>
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
        "SOAPAction": "http://ar.gov.afip.dif.FEV1/FECAESolicitar"
    }

    session = requests.Session()
    session.mount("https://", TLSAdapter())

    r = session.post(wsfe_url, data=soap_body.encode("utf-8"), headers=headers, timeout=25)

    if r.status_code != 200:
        raise Exception(f"WSFE devolvió {r.status_code}: {r.text}")

    # -------------------------------------------
    # 5) Parsear CAE + Vencimiento
    # -------------------------------------------
    tree = ET.fromstring(r.text)

    cae = None
    vencimiento = None

    for elem in tree.iter():
        if elem.tag.endswith("CAE"):
            cae = elem.text
        if elem.tag.endswith("CAEFchVto"):
            vencimiento = elem.text

    # Verificar errores
    errores = []
    for elem in tree.iter():
        if elem.tag.endswith("Err"):
            code = elem.findtext(".//Code")
            msg = elem.findtext(".//Msg")
            if code or msg:
                errores.append(f"{code}: {msg}")

    if errores:
        raise Exception(" | ".join(errores))

    if not cae:
        raise Exception("AFIP no devolvió CAE")

    return {
        "cbte_nro": cbte_nro,
        "cae": cae,
        "vencimiento": vencimiento,
        "tipo_cbte": tipo_cbte,
        "pto_vta": pto_vta
    }
