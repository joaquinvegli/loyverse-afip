# loyverse_api.py
from datetime import date, datetime
from typing import Dict, List
from collections import defaultdict

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from loyverse import (
    get_receipts_between,
    normalize_receipt,
    get_customer,
)

from json_db import obtener_factura, obtener_nota_credito

router = APIRouter(prefix="/api", tags=["ventas"])


# ======================================================
# UTILS
# ======================================================
def parse_fecha(fecha: str) -> datetime:
    return datetime.fromisoformat(fecha.replace("Z", "+00:00"))


# ======================================================
# LISTAR VENTAS + REEMBOLSOS (RELACIONADOS)
# ======================================================
@router.get("/ventas")
async def listar_ventas(
    desde: date = Query(...),
    hasta: date = Query(...),
):
    receipts_raw = await get_receipts_between(desde, hasta)

    if not isinstance(receipts_raw, list):
        return JSONResponse(
            status_code=500,
            content={"error": "Respuesta inválida de Loyverse"},
        )

    ventas = []
    reembolsos = []

    for r in receipts_raw:
        rec = normalize_receipt(r)

        if rec["receipt_type"] == "SALE":
            ventas.append(rec)
        elif rec["receipt_type"] == "REFUND":
            reembolsos.append(rec)

    # ======================================================
    # INDEXAR REEMBOLSOS POR PRODUCTO
    # ======================================================
    refunds_by_product = defaultdict(list)

    for ref in reembolsos:
        for item in ref["items"]:
            refunds_by_product[item["nombre"]].append(ref)

    resultado = []

    # ======================================================
    # PROCESAR VENTAS
    # ======================================================
    for sale in ventas:
        sale_date = parse_fecha(sale["fecha"])

        total_refund = 0.0
        refunded_items = []
        items_facturables = []

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

                    importe = round(ref_qty * unit_price, 2)
                    total_refund += importe
                    qty_left -= ref_qty

                    refunded_items.append({
                        "nombre": item["nombre"],
                        "cantidad": ref_qty,
                        "importe": importe,
                        "refund_receipt_id": ref["receipt_id"],
                    })

            if qty_left > 0:
                items_facturables.append({
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
            "refund_status": refund_status,
            "refunded_amount": total_refund,
            "max_facturable": max_facturable,
            "items_facturables": items_facturables,
            "refunded_items": refunded_items,
            "already_invoiced": factura is not None,
            "invoice": factura,
        })

        resultado.append(sale)

    # ======================================================
    # PROCESAR REEMBOLSOS (VINCULAR A VENTA)
    # ======================================================
    for ref in reembolsos:
        ref_date = parse_fecha(ref["fecha"])
        refund_total = ref["total"]

        original_sale_id = None

        for sale in ventas:
            sale_date = parse_fecha(sale["fecha"])
            if sale_date >= ref_date:
                continue

            # Match por producto
            sale_products = {i["nombre"] for i in sale["items"]}
            refund_products = {i["nombre"] for i in ref["items"]}

            if sale_products & refund_products:
                original_sale_id = sale["receipt_id"]
                break

        nota_credito = obtener_nota_credito(ref["receipt_id"])

        ref.update({
            "original_sale_id": original_sale_id,
            "refund_amount": refund_total,
            "refund_status": "REFUND",
            "already_invoiced": nota_credito is not None,
            "invoice": nota_credito,
        })

        resultado.append(ref)

    # ======================================================
    # ORDEN FINAL (más nuevo primero)
    # ======================================================
    resultado.sort(key=lambda x: x["fecha"], reverse=True)

    return resultado
