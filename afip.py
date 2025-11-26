import os
from afipws.wsaa import WSAA
from afipws.wsfev1 import WSFEv1

def init_afip():
    # Cargamos certificados desde variables de entorno
    cert = os.getenv("AFIP_CERT_CRT")
    key = os.getenv("AFIP_CERT_KEY")

    # Guardamos temporalmente en archivos (Render lo permite)
    with open("temp_cert.crt", "w") as f:
        f.write(cert)

    with open("temp_key.key", "w") as f:
        f.write(key)

    return "temp_cert.crt", "temp_key.key"


def facturar_prueba():
    cert_file, key_file = init_afip()

    # 1) WSAA – Autenticación
    wsaa = WSAA()
    ta = wsaa.create_tra(service="wsfe")
    wsaa.sign_tra(tra=ta, cert=cert_file, private_key=key_file)
    token, sign = wsaa.call_wsaa(ta, "https://wsaa.afip.gob.ar/ws/services/LoginCms")

    # 2) WSFE – Factura
    wsfe = WSFEv1()
    wsfe.Cuit = int(os.getenv("AFIP_CUIT"))
    wsfe.Token = token
    wsfe.Sign = sign
    wsfe.Url = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"

    # Obtener último número
    pto_vta = int(os.getenv("AFIP_PTO_VTA", "1"))
    tipo_cbte = 11  # Factura C

    last = wsfe.FECompUltimoAutorizado(pto_vta, tipo_cbte)
    next_number = last + 1

    # Cargar Factura tipo C simple
    wsfe.CrearFactura(
        concepto=1,       # Productos
        tipo_doc=99,      # Consumidor final
        nro_doc=0,
        tipo_cbte=tipo_cbte,
        punto_vta=pto_vta,
        cbte_nro=next_number,
        imp_total=1000.00,
        imp_neto=1000.00,
    )

    cae = wsfe.CAESolicitar()

    return {"numero": next_number, "cae": cae}
