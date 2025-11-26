import os
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def test_afip_connection():
    """
    Prueba mínima: obtener token desde WSAA y llamar CompUltimoAutorizado en WSFE.
    """

    afip_private_key = os.environ.get("AFIP_CERT_KEY")
    afip_cert = os.environ.get("AFIP_CERT_CRT")
    cuit = os.environ.get("AFIP_CUIT")
    pto_vta = os.environ.get("AFIP_PTO_VTA")

    if not afip_private_key:
        raise Exception("AFIP_CERT_KEY no está definida")
    if not afip_cert:
        raise Exception("AFIP_CERT_CRT no está definida")
    if not cuit:
        raise Exception("AFIP_CUIT no está definida")
    if not pto_vta:
        raise Exception("AFIP_PTO_VTA no está definida")

    pto_vta = int(pto_vta)

    # ======================
    # WSAA AUTENTICACIÓN
    # ======================
    wsaa = WSAA()
    wsaa.HOMO = False      # PRODUCCIÓN
    wsaa.Production = True

    wsaa.key = afip_private_key
    wsaa.crt = afip_cert

    ta = wsaa.Autenticar("wsfe", "TA.xml")

    if wsaa.Excepcion:
        raise Exception(f"WSAA ERROR: {wsaa.Excepcion}")

    token = wsaa.Token
    sign = wsaa.Sign

    # ======================
    # WSFE
    # ======================
    wsfe = WSFEv1()
    wsfe.HOMO = False
    wsfe.Production = True
    wsfe.Cuit = int(cuit)
    wsfe.Token = token
    wsfe.Sign = sign

    # Consulta básica
    wsfe.CompUltimoAutorizado(11, pto_vta)

    if wsfe.ErrMsg:
        raise Exception(f"WSFE devolvió error: {wsfe.ErrMsg}")

    return {
        "ultimo_cbte": wsfe.CbteNro,
        "pto_vta": pto_vta,
        "cuit": cuit
    }
