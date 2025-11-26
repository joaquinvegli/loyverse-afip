import os
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1

def init_afip_files():
    # Carga de certificados desde variables de entorno
    cert_text = os.getenv("AFIP_CERT_CRT")
    key_text = os.getenv("AFIP_CERT_KEY")

    # Guardar temporalmente los certificados en archivos locales
    cert_path = "cert-temp.crt"
    key_path = "key-temp.key"

    with open(cert_path, "w") as f:
        f.write(cert_text)

    with open(key_path, "w") as f:
        f.write(key_text)

    return cert_path, key_path

def facturar_prueba():
    cert_path, key_path = init_afip_files()

    cuit = int(os.getenv("AFIP_CUIT"))
    pto_vta = int(os.getenv("AFIP_PTO_VTA", "1"))
    tipo_cbte = 11  # Factura C

    # WSAA: autenticación
    wsaa = WSAA()
    tra = wsaa.CreateTRA("wsfe")

    cms = wsaa.SignTRA(tra, cert_path, key_path)
    ta = wsaa.CallWSAA(cms)

    token = wsaa.ObtenerTagXml(ta, "token")
    sign = wsaa.ObtenerTagXml(ta, "sign")

    # WSFE: facturación
    wsfe = WSFEv1()
    wsfe.Cuit = cuit
    wsfe.Token = token
    wsfe.Sign = sign

    # Último comprobante
    last = wsfe.CompUltimoAutorizado(pto_vta, tipo_cbte)
    cbte_nro = last[1] + 1

    # Crear factura C de prueba por $1000
    wsfe.CrearFactura(
        concepto=1,           # Productos
        tipo_doc=99,          # Consumidor final
        nro_doc=0,
        tipo_cbte=tipo_cbte,
        punto_vta=pto_vta,
        cbte_nro=cbte_nro,
        imp_total=1000.00,
        imp_neto=1000.00,
    )

    cae = wsfe.CAESolicitar()

    return {
        "numero": cbte_nro,
        "cae": cae
    }

