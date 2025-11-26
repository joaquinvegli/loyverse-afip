import os
import datetime
import base64
from M2Crypto import X509, SMIME, BIO
from zeep import Client

CUIT = int(os.getenv("AFIP_CUIT"))
CERT_CRT = os.getenv("AFIP_CERT_CRT")
CERT_KEY = os.getenv("AFIP_CERT_KEY")

WSAA_WSDL = "https://wsaa.afip.gov.ar/ws/services/LoginCms?WSDL"
WSFE_WSDL = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"


def generar_TA():
    """
    Genera el Ticket de Acceso firmando el TRA con CMS PKCS7 (FORMATO CORRECTO PARA AFIP)
    """

    # Armado del TRA
    tra = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>{int(datetime.datetime.now().timestamp())}</uniqueId>
    <generationTime>{(datetime.datetime.now() - datetime.timedelta(minutes=10)).isoformat()}</generationTime>
    <expirationTime>{(datetime.datetime.now() + datetime.timedelta(minutes=10)).isoformat()}</expirationTime>
  </header>
  <service>wsfe</service>
</loginTicketRequest>
"""

    bio_tra = BIO.MemoryBuffer(tra.encode("utf-8"))

    # Cargar certificado y key desde las variables de entorno
    bio_cert = BIO.MemoryBuffer(CERT_CRT.encode())
    x509 = X509.load_cert_bio(bio_cert)

    bio_key = BIO.MemoryBuffer(CERT_KEY.encode())

    # Preparar SMIME
    smime = SMIME.SMIME()
    smime.load_key_bio(bio_key, bio_cert)

    # Firmar CMS correctamente (PKCS7, DER)
    pkcs7 = smime.sign(bio_tra, flags=SMIME.PKCS7_BINARY)
    out = BIO.MemoryBuffer()
    pkcs7.write_der(out)

    cms = base64.b64encode(out.read()).decode("utf-8")

    # Llamada a WSAA
    client = Client(WSAA_WSDL)
    ta = client.service.loginCms(cms)

    return ta["credentials"]["token"], ta["credentials"]["sign"]


def test_afip_connection():
    try:
        token, sign = generar_TA()

        client = Client(WSFE_WSDL)

        result = client.service.FECompUltimoAutorizado(
            Auth={"Token": token, "Sign": sign, "Cuit": CUIT},
            PtoVta=3,    # punto de venta
            CbteTipo=6   # Factura B (cambiar si querés)
        )

        return {
            "status": "ok",
            "ultimo": result.CbteNro,
            "mensaje": "Conexión correcta a AFIP producción."
        }

    except Exception as e:
        return {"status": "error", "detalle": str(e)}
