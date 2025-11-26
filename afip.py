import os
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


# Rutas donde Render monta los Secret Files
KEY_PATH = "/etc/secrets/afip.key"
CRT_PATH = "/etc/secrets/afip.crt"


def test_afip_connection():
    """
    Test mínimo de conexión WSAA + WSFE en producción
    """

    if not os.path.exists(KEY_PATH):
        raise Exception(f"No existe la clave privada: {KEY_PATH}")

    if not os.path.exists(CRT_PATH):
        raise Exception(f"No existe el certificado: {CRT_PATH}")

    cuit = os.environ.get("AFIP_CUIT")
    if not cuit:
        raise Exception("Falta la variable AFIP_CUIT")

    # ============================
    # WSAA - Autenticación
    # ============================
    wsaa = WSAA()
    wsaa.HOMO = False           # siempre producción
    wsaa.Production = True

    cert = open(CRT_PATH).read()
    key = open(KEY_PATH).read()

    wsaa.LoginCMS(
        Certificado=cert,
        PrivateKey=key,
        Service="wsfe"
    )

    if wsaa.Excepcion:
        raise Exception(f"WSAA Error: {wsaa.Excepcion}")

    token = wsaa.Token
    sign = wsaa.Sign

    # ============================
    # WSFE - Test básico
    # ============================
    wsfe = WSFEv1()
    wsfe.HOMO = False
    wsfe.Production = True

    wsfe.Cuit = int(cuit)
    wsfe.Token = token
    wsfe.Sign = sign

    # solo obtener último comprobante autorizado para verificar permisos
    punto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))
    tipo_cbte = 11  # factura C

    wsfe.CompUltimoAutorizado(tipo_cbte, punto_vta)

    if wsfe.ErrMsg:
        raise Exception(f"WSFE Error: {wsfe.ErrMsg}")

    return {
        "estado": "OK",
        "ultimo_cbte": wsfe.CbteNro,
        "token_inicio": wsaa.Token[:40] + "..."
    }
