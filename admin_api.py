# admin_api.py
from datetime import date, datetime
from collections import defaultdict
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
import asyncio
import os
import httpx

from loyverse import get_receipts_between, normalize_receipt, get_customer

router = APIRouter(prefix="/api/admin", tags=["admin"])

BASE_URL = "https://api.loyverse.com/v1.0"
TOKEN = os.environ.get("LOYVERSE_TOKEN")

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

async def get_employees() -> dict:
    """Retorna dict {employee_id: nombre}"""
    headers = {"Authorization": f"Bearer {TOKEN}"}
    url = f"{BASE_URL}/employees?limit=250"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            return {}
        empleados = r.json().get("employees", [])
        return {
            e["id"]: f"{e.get('first_name', '')} {e.get('last_name', '')}".strip() or "Sin nombre"
            for e in empleados
        }


@router.get("/resumen")
async def resumen_admin(
    desde: date = Query(...),
    hasta: date = Query(...),
):
    from json_db import obtener_factura

    receipts_raw = await get_receipts_between(desde, hasta)
    if not isinstance(receipts_raw, list):
        return JSONResponse(status_code=500, content={"error": "Error al obtener ventas"})

    # Fetch clientes faltantes
    customer_ids_faltantes = list({
        r["customer_id"]
        for r in receipts_raw
        if r.get("customer_id") and not r.get("customer")
    })
    if customer_ids_faltantes:
        clientes_fetched = await asyncio.gather(*[get_customer(cid) for cid in customer_ids_faltantes])
        clientes_map = {cid: data for cid, data in zip(customer_ids_faltantes, clientes_fetched) if data}
        for r in receipts_raw:
            if r.get("customer_id") and not r.get("customer"):
                cliente = clientes_map.get(r["customer_id"])
                if cliente:
                    r["customer"] = cliente

    # Fetch empleados
    employees_map = await get_employees()

    # Normalizar
    sales = []
    refunds = []
    for r in receipts_raw:
        n = normalize_receipt(r)
        n["employee_id"] = r.get("employee_id")
        n["employee_name"] = employees_map.get(r.get("employee_id"), "Sin asignar")
        if n["receipt_type"] == "SALE":
            sales.append(n)
        elif n["receipt_type"] == "REFUND":
            refunds.append(n)

    # ── MÉTRICAS GENERALES ──
    total_ventas = len(sales)
    monto_total_real = sum(s["total"] or 0 for s in sales) - sum(r["total"] or 0 for r in refunds)
    monto_total_refunds = sum(r["total"] or 0 for r in refunds)
    ticket_promedio = round(monto_total_real / total_ventas, 2) if total_ventas else 0

    # Facturado vs no facturado
    monto_facturado = 0
    monto_no_facturado = 0
    cant_facturadas = 0
    cant_no_facturadas = 0
    for s in sales:
        factura = obtener_factura(s["receipt_id"])
        if factura:
            monto_facturado += factura.get("total", 0)
            cant_facturadas += 1
        else:
            monto_no_facturado += s["total"] or 0
            cant_no_facturadas += 1

    # ── VENTAS POR HORA ──
    ventas_por_hora = defaultdict(lambda: {"cantidad": 0, "monto": 0})
    for s in sales:
        try:
            dt = datetime.fromisoformat(s["fecha"].replace("Z", "+00:00"))
            hora_arg = (dt.hour - 3) % 24
            ventas_por_hora[hora_arg]["cantidad"] += 1
            ventas_por_hora[hora_arg]["monto"] += s["total"] or 0
        except Exception:
            pass

    horas_labels = [f"{h:02d}:00" for h in range(24)]
    horas_data = [
        {"hora": f"{h:02d}:00", "cantidad": ventas_por_hora[h]["cantidad"], "monto": round(ventas_por_hora[h]["monto"], 2)}
        for h in range(24)
    ]

    # ── VENTAS POR DÍA DE SEMANA ──
    ventas_por_dia = defaultdict(lambda: {"cantidad": 0, "monto": 0})
    for s in sales:
        try:
            dt = datetime.fromisoformat(s["fecha"].replace("Z", "+00:00"))
            dia = dt.weekday()  # 0=lunes
            ventas_por_dia[dia]["cantidad"] += 1
            ventas_por_dia[dia]["monto"] += s["total"] or 0
        except Exception:
            pass

    dias_data = [
        {"dia": DIAS_SEMANA[d], "cantidad": ventas_por_dia[d]["cantidad"], "monto": round(ventas_por_dia[d]["monto"], 2)}
        for d in range(7)
    ]

    # ── MÉTODOS DE PAGO ──
    pagos_agg = defaultdict(lambda: {"cantidad": 0, "monto": 0})
    for s in sales:
        for p in s.get("pagos", []):
            nombre = p.get("nombre") or p.get("tipo") or "Otro"
            pagos_agg[nombre]["cantidad"] += 1
            pagos_agg[nombre]["monto"] += p.get("monto") or 0

    pagos_data = [
        {"metodo": k, "cantidad": v["cantidad"], "monto": round(v["monto"], 2)}
        for k, v in sorted(pagos_agg.items(), key=lambda x: -x[1]["monto"])
    ]

    # ── PRODUCTOS MÁS VENDIDOS ──
    productos_agg = defaultdict(lambda: {"cantidad": 0, "monto": 0})
    for s in sales:
        for item in s.get("items", []):
            nombre = item.get("nombre") or "Sin nombre"
            productos_agg[nombre]["cantidad"] += item.get("cantidad") or 0
            productos_agg[nombre]["monto"] += item.get("precio_total_item") or 0

    top_productos_cantidad = sorted(
        [{"nombre": k, "cantidad": v["cantidad"], "monto": round(v["monto"], 2)} for k, v in productos_agg.items()],
        key=lambda x: -x["cantidad"]
    )[:15]

    top_productos_monto = sorted(
        [{"nombre": k, "cantidad": v["cantidad"], "monto": round(v["monto"], 2)} for k, v in productos_agg.items()],
        key=lambda x: -x["monto"]
    )[:15]

    # ── VENTAS POR EMPLEADO ──
    empleados_agg = defaultdict(lambda: {"cantidad": 0, "monto": 0})
    for s in sales:
        nombre = s.get("employee_name") or "Sin asignar"
        empleados_agg[nombre]["cantidad"] += 1
        empleados_agg[nombre]["monto"] += s["total"] or 0

    empleados_data = [
        {"empleado": k, "cantidad": v["cantidad"], "monto": round(v["monto"], 2)}
        for k, v in sorted(empleados_agg.items(), key=lambda x: -x[1]["monto"])
    ]

    # ── VENTAS POR DÍA (serie temporal) ──
    ventas_por_fecha = defaultdict(lambda: {"cantidad": 0, "monto": 0})
    for s in sales:
        try:
            dt = datetime.fromisoformat(s["fecha"].replace("Z", "+00:00"))
            fecha_arg = (dt - __import__("datetime").timedelta(hours=3)).strftime("%d/%m")
            ventas_por_fecha[fecha_arg]["cantidad"] += 1
            ventas_por_fecha[fecha_arg]["monto"] += s["total"] or 0
        except Exception:
            pass

    serie_diaria = [
        {"fecha": k, "cantidad": v["cantidad"], "monto": round(v["monto"], 2)}
        for k, v in sorted(ventas_por_fecha.items(), key=lambda x: x[0])
    ]

    return {
        "resumen": {
            "total_ventas": total_ventas,
            "monto_total_real": round(monto_total_real, 2),
            "monto_facturado": round(monto_facturado, 2),
            "monto_no_facturado": round(monto_no_facturado, 2),
            "monto_total_refunds": round(monto_total_refunds, 2),
            "ticket_promedio": ticket_promedio,
            "cant_facturadas": cant_facturadas,
            "cant_no_facturadas": cant_no_facturadas,
            "total_reembolsos": len(refunds),
        },
        "por_hora": horas_data,
        "por_dia_semana": dias_data,
        "serie_diaria": serie_diaria,
        "metodos_pago": pagos_data,
        "top_productos_cantidad": top_productos_cantidad,
        "top_productos_monto": top_productos_monto,
        "por_empleado": empleados_data,
    }
