import os
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def facturar_prueba():
    """
    Prueba mínima de conexión: WSAA (token/sign) + WSFE (CAE).
    Compatible con versiones antiguas de pyafipws.
    """

    cert = os.environ.get("AFIP_CERT_CRT")
    key = os.environ.get("AFIP_CERT_KEY")
    cuit = os.environ.get("AFIP_CUIT")
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))
    alias = "default"

    if not cert:
        raise Exception("AFIP_CERT_CRT no está definida")

    if not key:
        raise Exception("AFIP_CERT_KEY no está definida")

    if not cuit:
        raise Exception("AFIP_CUIT no está definida")

    # -------------------------
    # WSAA – AUTENTICACIÓN
    # -------------------------
    wsaa = WSAA()
    wsaa.HOMO = False          # Siempre producción
    wsaa.Production = True

    # Método compatible con versiones antiguas:
    # Autenticar(CRT, KEY, wsdl, ta)
    ta = f"TA-{alias}.xml"

    wsaa.Autenticar(cert, key, "wsaa", ta)

    if wsaa.Excepcion:
        raise Exception(f"WSAA Error: {wsaa.Excepcion}")

    token = wsaa.Token
    sign = wsaa.Sign

    # -------------------------
    # WSFE – FACTURACIÓN
    # -------------------------
    wsfe = WSFEv1()
    wsfe.HOMO = False
    wsfe.Production = True
    wsfe.Cuit = int(cuit)

    wsfe.Token = token
    wsfe.Sign = sign

    tipo_cbte = 11  # Factura C
    wsfe.CompUltimoAutorizado(tipo_cbte, pto_vta)
    ultimo = wsfe.CbteNro

    # -------------------------
    # Factura de prueba
    # -------------------------
    nuevo = ultimo + 1

    wsfe.Inicio = nuevo
    wsfe.CantReg = 1
    wsfe.Nro = nuevo

    wsfe.Concepto = 1         # Producto
    wsfe.TipoDoc = 99         # Consumidor Final
    wsfe.NroDoc = 0
    wsfe.FchCbte = wsfe.FechadeHoy()

    wsfe.MonedaId = "PES"
    wsfe.MonedaCotiz = 1

    wsfe.ImpNeto = 1
    wsfe.ImpIVA = 0
    wsfe.ImpTrib = 0
    wsfe.ImpOpEx = 0
    wsfe.ImpTotal = 1

    # Detalle mínimo
    wsfe.Detalle = [{
        "Qty": 1,
        "Item": "Prueba API",
        "ImpTotal": 1,
    }]

    wsfe.CAESolicitar()

    if wsfe.Excepcion:
        raise Exception(f"WSFE error: {wsfe.Excepcion}")

    if wsfe.ErrMsg:
        raise Exception(f"AFIP devolvió error: {wsfe.ErrMsg}")

    return {
        "resultado": wsfe.Resultado,
        "cae": wsfe.CAE,
        "vencimiento": wsfe.Vencimiento,
        "numero": wsfe.Nro,
    }
