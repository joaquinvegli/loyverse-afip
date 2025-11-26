import os
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1

def facturar_prueba():
    """
    Genera una factura mínima para probar autenticación y WSFE.
    NO crea facturas reales porque monto = 1 y es tipo prueba manual.
    """

    # =====================================================
    # 1. OBTENER VARIABLES DE ENTORNO
    # =====================================================

    afip_private_key = os.environ.get("AFIP_PRIVATE_KEY")
    afip_cert = os.environ.get("AFIP_CERT_CRT")

    cuit = os.environ.get("AFIP_CUIT")
    alias = os.environ.get("AFIP_ALIAS", "default")

    if not afip_private_key:
        raise Exception("AFIP_PRIVATE_KEY no está definida")

    if not afip_cert:
        raise Exception("AFIP_CERT_CRT no está definida")

    if not cuit:
        raise Exception("AFIP_CUIT no está definida")

    # =====================================================
    # 2. WSAA – AUTENTICACIÓN
    # =====================================================

    wsaa = WSAA()

    # Fuerzo **SIEMPRE** MODO PRODUCCIÓN
    wsaa.HOMO = False
    wsaa.Production = True

    # Cargo clave y certificado directamente desde variables
    wsaa.key = afip_private_key
    wsaa.crt = afip_cert

    # Archivo temporal para el ticket
    ta_xml = f"TA-{alias}.xml"

    # Solicito TA al WSAA oficial
    ta = wsaa.Autenticar(
        servicio="wsfe",
        ta_xml=ta_xml,
    )

    if wsaa.Excepcion:
        raise Exception(f"Error WSAA: {wsaa.Excepcion}")

    token = wsaa.Token
    sign = wsaa.Sign

    # =====================================================
    # 3. WSFEv1 – FACTURACIÓN
    # =====================================================

    wsfe = WSFEv1()
    wsfe.Cuit = int(cuit)

    # Fuerzo producción
    wsfe.HOMO = False
    wsfe.Production =
