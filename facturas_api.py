# facturas_api.py
from fastapi import APIRouter
from typing import Optional
from json_db import _load_db

router = APIRouter()

@router.get("/api/facturas")
def listar_facturas(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    cliente: Optional[str] = None,
    nro: Optional[str] = None,
):
    """
    Devuelve facturas y notas de crédito de la DB.
    Filtros opcionales:
      - desde / hasta: "DD/MM/YYYY"
      - cliente: búsqueda parcial por nombre
      - nro: número de comprobante (cbte_nro)
    """
    db = _load_db()
    facturas = db.get("facturas", {})
    notas = db.get("notas_credito", {})

    # Construir lista de facturas enriquecida
    resultado = []
    for receipt_id, f in facturas.items():
        # Buscar nota de crédito asociada a esta factura
        nc_asociada = None
        for refund_id, nc in notas.items():
            asociada_a = nc.get("asociada_a", {})
            if asociada_a.get("sale_receipt_id") == receipt_id:
                nc_asociada = {
                    "refund_receipt_id": refund_id,
                    "cbte_nro": nc.get("cbte_nro"),
                    "pto_vta": nc.get("pto_vta"),
                    "cae": nc.get("cae"),
                    "fecha": nc.get("fecha"),
                    "monto": nc.get("monto"),
                    "items": nc.get("items", []),
                }
                break

        resultado.append({
            "receipt_id": receipt_id,
            "cbte_nro": f.get("cbte_nro"),
            "pto_vta": f.get("pto_vta", 4),
            "cae": f.get("cae"),
            "fecha": f.get("fecha"),
            "vencimiento": f.get("vencimiento"),
            "cliente_nombre": f.get("cliente_nombre", "Consumidor Final"),
            "cliente_dni": f.get("cliente_dni"),
            "cliente_cuit": f.get("cliente_cuit"),
            "cliente_domicilio": f.get("cliente_domicilio"),
            "email_cliente": f.get("email_cliente", ""),
            "total": f.get("total", 0),
            "drive_url": f.get("drive_url"),
            "nota_credito": nc_asociada,
        })

    # Ordenar por cbte_nro descendente
    resultado.sort(key=lambda x: x["cbte_nro"] or 0, reverse=True)

    # Filtro por fecha
    if desde:
        resultado = [f for f in resultado if _fecha_gte(f["fecha"], desde)]
    if hasta:
        resultado = [f for f in resultado if _fecha_lte(f["fecha"], hasta)]

    # Filtro por cliente
    if cliente:
        q = cliente.lower()
        resultado = [
            f for f in resultado
            if q in (f["cliente_nombre"] or "").lower()
            or q in (f["cliente_dni"] or "")
            or q in (f["cliente_cuit"] or "")
        ]

    # Filtro por número de comprobante
    if nro:
        resultado = [f for f in resultado if str(f["cbte_nro"]) == nro.strip()]

    return {"facturas": resultado, "total": len(resultado)}


def _parse_fecha(fecha_str: str):
    """Convierte 'DD/MM/YYYY' a (yyyy, mm, dd) para comparar."""
    try:
        d, m, y = fecha_str.split("/")
        return (int(y), int(m), int(d))
    except Exception:
        return (0, 0, 0)

def _fecha_gte(fecha: str, desde: str):
    """fecha >= desde, ambas en 'DD/MM/YYYY'"""
    return _parse_fecha(fecha) >= _parse_fecha(desde)

def _fecha_lte(fecha: str, hasta: str):
    """fecha <= hasta, ambas en 'DD/MM/YYYY'"""
    return _parse_fecha(fecha) <= _parse_fecha(hasta)
