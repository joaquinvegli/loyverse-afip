import os
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def facturar_prueba():
    """
    Factura mínima para probar WSAA + WSFE en PRODUCCIÓN.
    """

    # ==============================
    # VARIABLES DE ENTORNO
    # ==============================
    private_key = os.environ.get("AFIP_CERT_KEY")
    certificate = os.environ.get("AFIP_CERT_CRT")
    cuit = os.environ.get("AFIP_CUIT")
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))

    if not private_key:
        raise Exception("AFIP_CERT_KEY no está definida")
    if not certificate:
        raise Exception("AFIP_CERT_CRT no está definida")
    if not cuit:
        raise Exception("AFIP_CUIT no está definida")

    # Guardar en disco (pyafipws lo necesita así)
    KEY_FILE = "afip.key"
    CRT_FILE = "afip.crt"

    with open(KEY_FILE, "w") as f:
        f.write(private_key)

    with open(CRT_FILE, "w") as f:
        f.write(certificate)

    # ==============================
    # 1. WSAA AUTENTICACIÓN
    # ==============================
    wsaa = WSAA()
    wsaa.HOMO = False
    wsaa.Production = True

    wsaa.key = private_key
    wsaa.crt = certificate

    ta = wsaa.Autenticar(
        servicio="wsfe",
        ta_xml="TA.xml"
    )

    if wsaa.Excepcion:
        raise Exception(f"WSAA Excepcion: {wsaa.Excepcion}")

    if wsaa.ErrMsg:
        raise Exception(f"WSAA Error: {wsaa.ErrMsg}")

    token = wsaa.Token
    sign = wsaa.Sign

    # ==============================
    # 2. WSFE
    # ==============================
    wsfe = WSFEv1()
    wsfe.HOMO = False
    wsfe.Production = True

    wsfe.Token = token
    wsfe.Sign = sign
    wsfe.Cuit = int(cuit)

    tipo_cbte = 11  # Factura C

    wsfe.CompUltimoAutorizado(tipo_cbte, pto_vta)
    ultimo = wsfe.CbteNro

    # ==============================
    # 3. FACTURA DE PRUEBA
    # ==============================
    wsfe.CantReg = 1
    wsfe.PtoVta = pto_vta
    wsfe.TipoCbte = tipo_cbte
    wsfe.CbteDesde = ultimo + 1
    wsfe.CbteHasta = ultimo + 1

    wsfe.Concepto = 1
    wsfe.TipoDoc = 99
    wsfe.NroDoc = 0

    wsfe.FchCbte = wsfe.FechadeHoy()
    wsfe.MonedaId = "PES"
    wsfe.MonedaCotiz = 1

    wsfe.ImpNeto = 1
    wsfe.ImpTotal = 1
    wsfe.ImpIVA = 0
    wsfe.ImpOpEx = 0
    wsfe.ImpTrib = 0

    wsfe.CAESolicitar()

    if wsfe.Excepcion:
        raise Exception(f"WSFE Excepcion: {wsfe.Excepcion}")

    if wsfe.ErrMsg:
        raise Exception(f"WSFE Error: {wsfe.ErrMsg}")

    return {
        "Resultado": wsfe.Resultado,
        "CAE": wsfe.CAE,
        "Vencimiento": wsfe.Vencimiento,
        "Numero": wsfe.CbteDesde,
    }
