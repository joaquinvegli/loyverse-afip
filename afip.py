import os
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1


def test_afip_connection():
    # === 1) RUTAS CORRECTAS ===
    key_path = "/etc/secrets/afip_new.key"
    crt_path = "/etc/secrets/afip_new.crt"

    if not os.path.exists(key_path):
        return {"error": f"No existe {key_path}"}

    if not os.path.exists(crt_path):
        return {"error": f"No existe {crt_path}"}

    # === 2) WSAA PRODUCCIÓN ===
    wsaa = WSAA()
    wsaa.HOMO = False  # producción

    try:
        # IMPORTANTE: pyafipws usa este orden: cert, key
        ta = wsaa.LoginCMS(crt_path, key_path)

        if wsaa.Excepcion:
            return {"error": f"WSAA error: {wsaa.Excepcion}"}

    except Exception as e:
        return {"error": f"Error LoginCMS(): {str(e)}"}

    # === 3) WSFE ===
    wsfe = WSFEv1()
    wsfe.HOMO = False
    wsfe.Token = wsaa.Token
    wsfe.Sign = wsaa.Sign

    cuit = os.environ.get("AFIP_CUIT")
    pto_vta = int(os.environ.get("AFIP_PTO_VTA", "1"))
    tipo_cbte = 11  # FACTURA C

    if not cuit:
        return {"error": "Variable AFIP_CUIT no definida"}

    wsfe.Cuit = int(cuit)

    try:
        wsfe.CompUltimoAutorizado(tipo_cbte, pto_vta)
        if wsfe.Excepcion:
            return {"error": wsfe.Excepcion}

    except Exception as e:
        return {"error": f"WSFE error: {str(e)}"}

    return {
        "status": "ok",
        "ultimo": wsfe.CbteNro,
        "token": wsaa.Token[:25] + "...",
        "sign": wsaa.Sign[:25] + "..."
    }
