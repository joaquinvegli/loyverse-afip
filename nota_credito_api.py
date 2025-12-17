from fastapi import APIRouter
from fastapi.responses import JSONResponse

from afip import wsfe_nota_credito_c
from json_db import obtener_factura, nota_credito_emitida, guardar_nota_credito

router = APIRouter(prefix="/api", tags=["nota_credito"])


@router.post("/nota_credito")
async def emitir_nota_credito(payload: dict):
    """
    Payload esperado desde frontend:
    {
      "refund_receipt_id": "2-0287",
      "sale_receipt_id": "2-0284",
      "cliente": { "dni": "...", "cuit": "...", "name": "...", "email": "..." },
      "items": [ { "nombre": "...", "cantidad": 1, "precio_unitario": 9000 } ],
      "total": 9000.0
    }
    """

    refund_id = payload.get("refund_receipt_id")
    sale_id = payload.get("sale_receipt_id")
    cliente = payload.get("cliente") or {}
    items = payload.get("items") or []
    total = float(payload.get("total") or 0)

    if not refund_id or not sale_id:
        return JSONResponse(status_code=400, content={"detail": "Falta refund_receipt_id o sale_receipt_id"})

    if total <= 0 or not items:
        return JSONResponse(status_code=400, content={"detail": "Total/items inválidos para NC"})

    # 1) Evitar doble emisión
    if nota_credito_emitida(refund_id):
        return JSONResponse(status_code=400, content={"detail": "Este reembolso ya tiene Nota de Crédito emitida"})

    # 2) Solo se emite NC si la venta original fue facturada
    factura = obtener_factura(sale_id)
    if not factura:
        return JSONResponse(status_code=400, content={
            "detail": "La venta original no está facturada. No corresponde emitir Nota de Crédito."
        })

    # 3) Convertir items a formato AFIP
    afip_items = []
    for it in items:
        afip_items.append({
            "descripcion": it["nombre"],
            "cantidad": it["cantidad"],
            "precio": it["precio_unitario"],
        })

    # 4) Emitir NC en AFIP (Nota de Crédito C = 13, asociada a Factura C = 11)
    try:
        nc = wsfe_nota_credito_c(
            cliente=cliente,
            items=afip_items,
            total=total,
            factura_asociada={"cbte_nro": factura["cbte_nro"], "pto_vta": factura["pto_vta"]},
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

    # 5) Guardar NC en DB (por refund_receipt_id)
    info = {
        "cbte_nro": nc["cbte_nro"],
        "pto_vta": nc["pto_vta"],
        "cae": nc["cae"],
        "vencimiento": nc["vencimiento"],
        "tipo_cbte": 13,
        "fecha": factura.get("fecha"),  # opcional
        "asociada_a": {
            "sale_receipt_id": sale_id,
            "factura_cbte_nro": factura["cbte_nro"],
            "factura_pto_vta": factura["pto_vta"],
        },
        "monto": total,
        "items": items,
    }
    guardar_nota_credito(refund_id, info)

    return {"status": "ok", "nota_credito": info}
