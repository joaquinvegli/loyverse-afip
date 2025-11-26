import base64
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1

class Afip:
    def __init__(self, cert, key, alias):
        self.cert = cert
        self.key = key
        self.alias = alias

    def crear_ticket(self):
        wsaa = WSAA()

        # *** PRODUCCIÓN ***
        wsaa.HOMO = False
        wsaa.WSDL = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"

        ta = wsaa.LoginCMS(
            self.cert,
            self.key,
            "wsfe"
        )
        return ta

    def crear_factura(self, ta, data):
        wsfe = WSFEv1()

        # *** PRODUCCIÓN ***
        wsfe.Conectar("https://servicios1.afip.gov.ar/wsfev1/service.asmx")

        wsfe.Cuit = int(data["cuit"])
        wsfe.Token = ta["token"]
        wsfe.Sign = ta["sign"]

        cbte = {
            "TipoComprobante": data["tipo_cbte"],
            "PuntoVenta": data["pto_vta"],
            "NumeroComprobante": data["numero"],
            "Concepto": data["concepto"],
            "TipoDocumento": data["tipo_doc"],
            "NumeroDocumento": data["nro_doc"],
            "ImporteTotal": data["total"],
            "ImporteNeto": data["neto"],
            "ImporteIVA": data["iva"],
            "FechaComprobante": data["fecha"],
            "Tributos": [],
            "Ivas": [
                {
                    "Id": data["iva_id"],
                    "BaseImp": data["neto"],
                    "Importe": data["iva"]
                }
            ]
        }

        resultado = wsfe.CrearFactura(**cbte)
        return resultado
