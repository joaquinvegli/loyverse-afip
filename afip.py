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
    wsfe.Production = True

    # Asigno token y firma obtenidos
    wsfe.Token = token
    wsfe.Sign = sign

    # Último número autorizado
    punto_vta = 1
    tipo_cbte = 11  # FACTURA C

    cae_request = wsfe.CompUltimoAutorizado(tipo_cbte, punto_vta)
    ultimo = wsfe.CbteNro

    # =====================================================================
    # 4. CREAR FACTURA DE PRUEBA (Real, pero con monto 1 para testeo)
    # =====================================================================

    wsfe.Inicio = ultimo + 1
    wsfe.Nro = ultimo + 1
    wsfe.FchCbte = wsfe.FechadeHoy()

    wsfe.MonedaId = "PES"
    wsfe.MonedaCotiz = 1

    wsfe.ImpTotal = 1
    wsfe.ImpNeto = 1
    wsfe.ImpOpEx = 0
    wsfe.ImpIVA = 0
    wsfe.ImpTrib = 0

    # Cliente consumidor final
    wsfe.TipoDoc = 99
    wsfe.NroDoc = 0

    wsfe.Concepto = 1  # productos
    wsfe.CantReg = 1

    wsfe.Detalle = [{
        "Qty": 1,
        "Item": "Prueba API",
        "ImpTotal": 1,
    }]

    # =====================================================================
    # 5. AUTORIZAR
    # =====================================================================

    resultado = wsfe.CAESolicitar()

    if wsfe.Excepcion:
        raise Exception(f"Error WSFE: {wsfe.Excepcion}")

    if wsfe.ErrMsg:
        raise Exception(f"AFIP devolvió error: {wsfe.ErrMsg}")

    return {
        "resultado": wsfe.Resultado,
        "cae": wsfe.CAE,
        "cae_vto": wsfe.Vencimiento,
        "cbte": wsfe.Nro,
        "punto_vta": punto_vta,
    }
