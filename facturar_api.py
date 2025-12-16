# loyverse_api.py
from datetime import date
from typing import Dict, List, Tuple, Any, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from loyverse import (
    get_receipts_between,
    normalize_receipt,
    get_customer,
)

# IMPORTANTE: consultar información de facturas
from json_db import obtener_factura

router = APIRouter(prefix="/api", tags=["ventas"])


# ============================================
# Función para limpiar el DNI (solo números)
# ============================================
def limpiar_dni(valor: str):
    if not valor:
        return None
    solo_numeros = "".join(c for c in valor if c.isdigit())
    return solo_numeros if solo_numeros else None


# ============================================
# Helpers: items -> mapa (nombre+precio) -> qty
# ============================================
def _item_key(nombre: str, precio_unitario: float) -> str:
    # clave estable para asociar devoluciones
    return f"{(nombre or '').strip().lower()}|{round(float(precio_unitario or 0), 2)}"


def _items_to_qtymap(items: List[dict]) -> Dict[str, float]:
    m: Dict[str, float] = {}
    for it in items or []:
        nombre = it.get("nombre") or it.get("name") or ""
        precio = it.get("precio_unitario") or it.get("price") or 0
        qty = it.get("cantidad") or it.get("quantity") or 0
        k = _item_key(nombre, precio)
        m[k] = m.get(k, 0) + float(qty)
    return m


def _qtymap_value(qtymap: Dict[str, float], items_lookup: Dict[str, Tuple[str, float]]) -> float:
    # calcula total por qtymap usando (nombre, precio_unitario) de items_lookup
    total = 0.0
    for k, qty in qtymap.items():
        if qty <= 0:
            continue
        _, precio = items_lookup.get(k, ("", 0.0))
        total += round(float(qty) * float(precio), 2)
    return round(total, 2)


def _build_items_lookup(items: List[dict]) -> Dict[str, Tuple[str, float]]:
    lookup: Dict[str, Tuple[str, float]] = {}
    for it in items or []:
        nombre = it.get("nombre") or it.get("name") or ""
        precio = float(it.get("precio_unitario") or it.get("price") or 0)
        lookup[_item_key(nombre, precio)] = (nombre, precio)
    return lookup


def _subtract_qtymap(base: Dict[str, float], sub: Dict[str, float]) -> Dict[str, float]:
    out = dict(base)
    for k, q in (sub or {}).items():
        out[k] = out.get(k, 0) - float(q)
        if out[k] <= 0:
            out.pop(k, None)
    return out


def _can_refund_match_sale(refund_qty: Dict[str, float], sale_remaining_qty: Dict[str, float]) -> bool:
    # El refund es "aplicable" si para cada item del refund hay qty suficiente en la venta
    for k, rq in refund_qty.items():
        if float(rq) <= 0:
            continue
        if sale_remaining_qty.get(k, 0) + 1e-9 < float(rq):
            return False
    return True


def _match_score(refund_qty: Dict[str, float], sale_remaining_qty: Dict[str, float]) -> float:
    # score = total qty coincidente (simple y robusto)
    score = 0.0
    for k, rq in refund_qty.items():
        score += min(float(rq), float(sale_remaining_qty.get(k, 0)))
    return score


def _build_items_facturables(remaining_qty: Dict[str, float], items_lookup: Dict[str, Tuple[str, float]]) -> List[dict]:
    # genera items facturables tipo [{nombre,cantidad,precio_unitario,precio_total_item}, ...]
    out: List[dict] = []
    for k, qty in remaining_qty.items():
        if qty <= 0:
            continue
        nombre, precio = items_lookup.get(k, ("", 0.0))
        total_item = round(float(qty) * float(precio), 2)
        out.append(
            {
                "nombre": nombre,
                "cantidad": float(qty) if float(qty) % 1 else int(qty),
                "precio_unitario": float(precio),
                "precio_total_item": total_item,
            }
        )
    return out


# ============================================
# LISTAR VENTAS ENTRE FECHAS (SALE + REFUND)
# ============================================
@router.get("/ventas")
async def listar_ventas(
    desde: date = Query(..., description="Fecha desde (YYYY-MM-DD)"),
    hasta: date = Query(..., description="Fecha hasta (YYYY-MM-DD)"),
):
    receipts_raw = await get_receipts_between(desde, hasta)

    if isinstance(receipts_raw, dict) and "error" in receipts_raw:
        return JSONResponse(status_code=400, content=receipts_raw)

    if not isinstance(receipts_raw, list):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Formato inesperado recibido desde Loyverse",
                "type": str(type(receipts_raw)),
                "data": receipts_raw,
            },
        )

    # 1) Normalizamos todo primero
    normalized: List[dict] = []
    for r in receipts_raw:
        v = normalize_receipt(r)

        # Estado de facturación (de nuestro JSON en Drive)
        receipt_id = v.get("receipt_id")
        info = obtener_factura(receipt_id) if receipt_id else None
        if info:
            v["already_invoiced"] = True
            v["invoice"] = info
        else:
            v["already_invoiced"] = False
            v["invoice"] = None

        normalized.append(v)

    # 2) Orden por fecha ascendente para asociar refund -> sale anterior
    def _dt_key(x: dict) -> str:
        # ISO string, suficiente para ordenar (viene tipo 2025-12-16T15:01:46.000Z)
        return x.get("fecha") or ""

    normalized.sort(key=_dt_key)

    # 3) Separamos SALES y REFUNDS
    sales: Dict[str, dict] = {}
    sale_order: List[str] = []

    for v in normalized:
        rid = v.get("receipt_id")
        rtype = (v.get("receipt_type") or "").upper()

        if not rid:
            continue

        # Inicializar flags comunes (para que el frontend no tenga que adivinar)
        v.setdefault("has_refund", False)
        v.setdefault("refund_type", "NONE")  # NONE | PARTIAL | TOTAL
        v.setdefault("refunded_total", 0.0)
        v.setdefault("facturable_total", float(v.get("total") or 0))
        v.setdefault("can_invoice", True)

        # Campos específicos de refund
        v.setdefault("refund_of", None)  # receipt_id de venta asociada
        v.setdefault("refund_total", 0.0)
        v.setdefault("linked_sale_already_invoiced", False)

        if rtype == "SALE":
            # guardamos estructura de la venta para matching
            items = v.get("items") or []
            qtymap = _items_to_qtymap(items)
            items_lookup = _build_items_lookup(items)

            sales[rid] = {
                "venta": v,
                "items_lookup": items_lookup,
                "sale_total": round(float(v.get("total") or 0), 2),
                "remaining_qty": dict(qtymap),  # va bajando con refunds asociados
                "refunded_total": 0.0,
                "refunds": [],  # lista de receipt_id refund asociados
            }
            sale_order.append(rid)

        elif rtype == "REFUND":
            # Los refunds nunca se facturan
            v["can_invoice"] = False
            v["refund_total"] = round(float(v.get("total") or 0), 2)

            refund_items = v.get("items") or []
            refund_qty = _items_to_qtymap(refund_items)

            # Buscar mejor venta candidata anterior (en el rango recibido)
            best_sale_id: Optional[str] = None
            best_score = 0.0

            # recorremos ventas previas en orden (ya están cargadas en sale_order)
            for sid in reversed(sale_order):
                s = sales.get(sid)
                if not s:
                    continue

                sale_v = s["venta"]
                # Solo asociar si la venta es anterior (por fecha string ISO)
                if (sale_v.get("fecha") or "") > (v.get("fecha") or ""):
                    continue

                # Validación fuerte por productos/cantidades restantes
                if not _can_refund_match_sale(refund_qty, s["remaining_qty"]):
                    continue

                sc = _match_score(refund_qty, s["remaining_qty"])
                if sc > best_score:
                    best_score = sc
                    best_sale_id = sid

                # si ya es match perfecto (todas las qty), cortamos rápido
                if sc >= sum(refund_qty.values()):
                    break

            if best_sale_id:
                s = sales[best_sale_id]

                # descontar quantities
                s["remaining_qty"] = _subtract_qtymap(s["remaining_qty"], refund_qty)

                # acumular refund total (por monto del receipt refund)
                s["refunded_total"] = round(float(s["refunded_total"]) + float(v["refund_total"]), 2)
                s["refunds"].append(v.get("receipt_id"))

                # marcar refund -> venta
                v["refund_of"] = best_sale_id
                v["linked_sale_already_invoiced"] = bool(s["venta"].get("already_invoiced"))

                # tipo refund (PARCIAL/TOTAL) relativo a la venta
                remaining_value = _qtymap_value(s["remaining_qty"], s["items_lookup"])
                if remaining_value <= 1e-6:
                    v["refund_type"] = "TOTAL"
                else:
                    v["refund_type"] = "PARTIAL"
            else:
                # no se pudo asociar (igual se lista como refund)
                v["refund_of"] = None
                v["refund_type"] = "UNKNOWN"

    # 4) Aplicar resultado de refunds a las ventas (en la venta misma)
    for sid, s in sales.items():
        venta = s["venta"]

        refunded_total = round(float(s["refunded_total"]), 2)
        remaining_value = _qtymap_value(s["remaining_qty"], s["items_lookup"])

        if refunded_total > 0:
            venta["has_refund"] = True
            venta["refunded_total"] = refunded_total
            venta["facturable_total"] = remaining_value
            venta["items_facturables"] = _build_items_facturables(s["remaining_qty"], s["items_lookup"])
            venta["refund_receipts"] = s["refunds"]

            if remaining_value <= 1e-6:
                venta["refund_type"] = "TOTAL"
            else:
                venta["refund_type"] = "PARTIAL"
        else:
            venta["has_refund"] = False
            venta["refund_type"] = "NONE"
            venta["refunded_total"] = 0.0
            venta["facturable_total"] = round(float(venta.get("total") or 0), 2)
            venta["items_facturables"] = None
            venta["refund_receipts"] = []

        # Reglas de facturación:
        # - si ya está facturada, NO se puede refacturar
        # - si refund TOTAL, no se puede facturar
        if bool(venta.get("already_invoiced")):
            venta["can_invoice"] = False
        elif venta["refund_type"] == "TOTAL":
            venta["can_invoice"] = False
        else:
            venta["can_invoice"] = True

    # 5) Devolvemos TODO (SALE + REFUND) con flags ya listos para frontend
    return normalized


# ============================================
# OBTENER DATOS DE UN CLIENTE (con DNI limpio)
# ============================================
@router.get("/clientes/{customer_id}")
async def obtener_cliente(customer_id: str):
    data = await get_customer(customer_id)

    if data is None:
        return {
            "exists": False,
            "id": customer_id,
            "name": None,
            "email": None,
            "phone": None,
            "dni": None,
        }

    dni_limpio = limpiar_dni(data.get("note"))

    return {
        "exists": True,
        "id": data.get("id"),
        "name": data.get("name"),
        "email": data.get("email"),
        "phone": data.get("phone_number"),
        "dni": dni_limpio,
    }


# ============================================
# DEBUG: Ver venta cruda
# ============================================
@router.get("/debug/venta/{receipt_id}")
async def debug_venta(receipt_id: str):
    from datetime import date, timedelta

    desde = date.today() - timedelta(days=365)
    hasta = date.today() + timedelta(days=1)

    receipts = await get_receipts_between(desde, hasta)

    for r in receipts:
        if r.get("receipt_number") == receipt_id:
            return r

    return {"error": "No se encontró ese recibo"}
