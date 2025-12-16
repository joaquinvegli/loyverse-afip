# loyverse_api.py
from datetime import date, datetime
from typing import List, Dict
from collections import defaultdict

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from loyverse import (
    get_receipts_between,
    normalize_receipt,
    get_customer,
)

from json_db import obtener_factura

router = APIRouter(prefix="/api", tags=["ventas"])


# ============================
# UTILIDADES
# ============================
def parse_fecha(fecha_str: str) -> datetime:
    return datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))


# ============================
# LISTAR VENTAS + REEMBOLSOS
# ============================
@router.get("/ventas")
async def listar_ventas(
    desde: date = Query(...),
    hasta: date = Query(...),
):
    receipts_raw = await get_receipts_between(desde, hasta)

    if not isinstance(receipts_raw, list):
        return JSONResponse(status_code=500, content={"error": "Respuesta inválida de Loyverse"})

    sales = []
    refunds = []

    for r in receipts_raw:
        if r.get("receipt_type") == "SALE":
            sales.append(normalize_receipt(r))
        elif r.get("receipt_type") == "REFUND":
            refunds.append(normalize_receipt(r))

    # ============================
    # INDEXAR REEMBOLSOS POR PRODUCTO
    # ============================
    refunds_by_product = defaultdict(list)

    for refund in refunds:
        for item in refund["items"]:
            refunds_by_product[item["nombre"]].append(refund)

    # ============================
    # PROCESAR VENTAS
    # ============================
    resultado = []

    for sale in sales:
        sale_date = parse_fecha(sale["fecha"])
        total_refund = 0
        refunded_items = []

        remaining_items = []

        for item in sale["items"]:
            qty_left = item["cantidad"]
            unit_price = item["precio_unitario"]

            posibles = refunds_by_product.get(item["nombre"], [])

            for ref in posibles:
                ref_date = parse_fecha(ref["fecha"])
                if ref_date <= sale_date:
                    continue

                for ref_item in ref["items"]:
                    if ref_item["nombre"] != item["nombre"]:
                        continue

                    ref_qty = min(qty_left, ref_item["cantidad"])
                    if ref_qty <= 0:
                        continue

                    importe = ref_qty * unit_price
                    total_refund += importe
                    qty_left -= ref_qty

                    refunded_items.append({
                        "nombre": item["nombre"],
                        "cantidad": ref_qty,
                        "importe": importe,
                        "refund_receipt": ref["receipt_id"]
                    })

            if qty_left > 0:
                remaining_items.append({
                    "nombre": item["nombre"],
                    "cantidad": qty_left,
                    "precio_unitario": unit_price,
                })

        max_facturable = round(sale["total"] - total_refund, 2)

        if total_refund == 0:
            refund_status = "NONE"
        elif max_facturable == 0:
            refund_status = "TOTAL"
        else:
            refund_status = "PARTIAL"

        factura = obtener_factura(sale["receipt_id"])

        sale.update({
            "refunded_amount": total_refund,
            "max_facturable": max_facturable,
            "refund_status": refund_status,
            "items_facturables": remaining_items,
            "already_invoiced": factura is not None,
            "invoice": factura,
        })

        resultado.append(sale)

    # ============================
    # AGREGAR REEMBOLSOS COMO TARJETAS
    # ============================
    for ref in refunds:
        ref.update({
            "refund_status": "REFUND",
            "already_invoiced": False,
            "invoice": None,
        })
        resultado.append(ref)

    # Ordenar por fecha DESC
    resultado.sort(key=lambda x: x["fecha"], reverse=True)

    return resultado
