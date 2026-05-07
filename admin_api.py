# admin_api.py
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
import json
import time
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
import asyncio
import os
import httpx
from pydantic import BaseModel
from supabase import create_client

from loyverse import get_receipts_between, normalize_receipt, get_customer

router = APIRouter(prefix="/api/admin", tags=["admin"])

BASE_URL = "https://api.loyverse.com/v1.0"
TOKEN = os.environ.get("LOYVERSE_TOKEN")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
SUPABASE_BUCKET = "facturas"
SUELDOS_DB_PATH = "db/sueldos_db.json"

EMPLOYEE_NAME_MAP = {
    "4c802b1a-6219-48b6-b7bc-8b9f674387cc": "Amparo",
    "56bdd969-f76a-4d1b-9119-367c1031965a": "Miranda",
    "ba7a64a1-9555-4344-b614-d420d1401340": "Agustina",
    "99da6a5f-3a40-4691-9077-501a5205a891": "Propietario",
}

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

def _require_admin_key(x_admin_key: str | None) -> None:
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Falta configurar ADMIN_API_KEY en el backend.")
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Clave admin invalida.")


class SalaryRequest(BaseModel):
    employee_id: str
    hourly_rate: float


class ShiftOverrideRequest(BaseModel):
    shift_id: str
    employee_id: str
    employee_name: str | None = None
    note: str | None = ""


def _get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY")
    return create_client(url, key)


def _default_sueldos_db() -> dict:
    return {
        "employee_names": EMPLOYEE_NAME_MAP.copy(),
        "hourly_rates": {},
        "shift_overrides": {},
    }


def _load_sueldos_db() -> dict:
    try:
        supabase = _get_supabase()
        url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(SUELDOS_DB_PATH)
        response = httpx.get(f"{url}?t={int(time.time())}", timeout=15, follow_redirects=True)
        if response.status_code in (400, 404):
            return _default_sueldos_db()
        response.raise_for_status()
        data = json.loads(response.text.strip() or "{}")
    except Exception:
        data = _default_sueldos_db()

    defaults = _default_sueldos_db()
    for key, value in defaults.items():
        if key not in data or not isinstance(data[key], type(value)):
            data[key] = value
    data["employee_names"] = {**EMPLOYEE_NAME_MAP, **data.get("employee_names", {})}
    return data


def _save_sueldos_db(data: dict) -> None:
    supabase = _get_supabase()
    payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    supabase.storage.from_(SUPABASE_BUCKET).upload(
        path=SUELDOS_DB_PATH,
        file=payload,
        file_options={"content-type": "application/json", "upsert": "true"},
    )


def _to_argentina_parts(iso_value: str | None) -> dict:
    dt = _parse_dt(iso_value)
    if not dt:
        return {"date": "", "time": ""}
    local = dt.astimezone(timezone(timedelta(hours=-3)))
    return {
        "date": local.strftime("%Y-%m-%d"),
        "time": local.strftime("%H:%M"),
    }


def _apply_salary_data(shift: dict, sueldos_db: dict) -> dict:
    override = sueldos_db.get("shift_overrides", {}).get(shift["shift_id"])
    original_employee_id = shift.get("employee_id")
    original_employee_name = sueldos_db["employee_names"].get(original_employee_id, shift.get("employee_name") or "Sin asignar")

    if override:
        employee_id = override.get("employee_id") or original_employee_id
        employee_name = override.get("employee_name") or sueldos_db["employee_names"].get(employee_id, "Sin asignar")
    else:
        employee_id = original_employee_id
        employee_name = original_employee_name

    hourly_rate = float(sueldos_db.get("hourly_rates", {}).get(employee_id, 0) or 0)
    hours = float(shift.get("hours") or 0)
    opened = _to_argentina_parts(shift.get("opened_at"))
    closed = _to_argentina_parts(shift.get("closed_at"))

    return {
        **shift,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "original_employee_id": original_employee_id,
        "original_employee_name": original_employee_name,
        "override": override,
        "date": opened["date"],
        "opened_time": opened["time"],
        "closed_time": closed["time"],
        "hourly_rate": hourly_rate,
        "pay": round(hours * hourly_rate, 2),
    }


def _summarize_sueldos(shifts: list[dict], sueldos_db: dict) -> list[dict]:
    summary = defaultdict(lambda: {"employee_id": "", "employee_name": "", "shifts": 0, "hours": 0.0, "hourly_rate": 0.0, "pay": 0.0})
    for shift in shifts:
        employee_id = shift.get("employee_id") or "sin_asignar"
        summary[employee_id]["employee_id"] = employee_id
        summary[employee_id]["employee_name"] = shift.get("employee_name") or "Sin asignar"
        summary[employee_id]["shifts"] += 1
        summary[employee_id]["hours"] = round(summary[employee_id]["hours"] + float(shift.get("hours") or 0), 2)
        summary[employee_id]["hourly_rate"] = float(sueldos_db.get("hourly_rates", {}).get(employee_id, 0) or 0)
        summary[employee_id]["pay"] = round(summary[employee_id]["pay"] + float(shift.get("pay") or 0), 2)
    return sorted(summary.values(), key=lambda item: item["employee_name"])


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


def _to_utc_range(desde: date, hasta: date) -> tuple[str, str]:
    inicio_arg = datetime(desde.year, desde.month, desde.day, 0, 0, 0, tzinfo=timezone(timedelta(hours=-3)))
    fin_arg = datetime(hasta.year, hasta.month, hasta.day, 23, 59, 59, tzinfo=timezone(timedelta(hours=-3)))
    return (
        inicio_arg.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        fin_arg.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _first_present(data: dict, keys: list[str]):
    for key in keys:
        if data.get(key) is not None:
            return data.get(key)
    return None


def _in_range(iso_value: str | None, start_utc: str, end_utc: str) -> bool:
    dt = _parse_dt(iso_value)
    start_dt = _parse_dt(start_utc)
    end_dt = _parse_dt(end_utc)
    if not dt or not start_dt or not end_dt:
        return False
    return start_dt <= dt <= end_dt


async def _fetch_loyverse_shifts(desde: date, hasta: date) -> dict:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    inicio_utc, fin_utc = _to_utc_range(desde, hasta)
    attempts = [
        ("opened_at", {"opened_at_min": inicio_utc, "opened_at_max": fin_utc}),
        ("created_at", {"created_at_min": inicio_utc, "created_at_max": fin_utc}),
        ("closed_at", {"closed_at_min": inicio_utc, "closed_at_max": fin_utc}),
        ("no_date_filter", {}),
    ]

    last_error = None
    async with httpx.AsyncClient(timeout=30) as client:
        for attempt_name, date_params in attempts:
            shifts = []
            cursor = None
            first_page_error = None

            while True:
                params = {"limit": 250, **date_params}
                if cursor:
                    params["cursor"] = cursor

                response = await client.get(f"{BASE_URL}/shifts", headers=headers, params=params)
                if response.status_code != 200:
                    first_page_error = {
                        "attempt": attempt_name,
                        "status": response.status_code,
                        "body": response.text[:1000],
                        "params": date_params,
                    }
                    break

                body = response.json()
                page_shifts = body.get("shifts", [])
                shifts.extend(page_shifts)

                cursor = body.get("cursor")
                if not cursor or len(page_shifts) < 250:
                    filtered = [
                        shift for shift in shifts
                        if _in_range(
                            _first_present(shift, ["opened_at", "opening_time", "open_time", "created_at"]),
                            inicio_utc,
                            fin_utc,
                        )
                    ]
                    return {
                        "attempt": attempt_name,
                        "shifts": filtered,
                        "raw_count": len(shifts),
                        "filtered_locally": len(filtered) != len(shifts),
                    }

            last_error = first_page_error

    return {"error": last_error or {"message": "No se pudo consultar Loyverse shifts"}}


def _name_from_employee_obj(employee: dict | None) -> str | None:
    if not employee:
        return None
    full_name = (
        employee.get("name")
        or f"{employee.get('first_name', '')} {employee.get('last_name', '')}".strip()
        or employee.get("email")
    )
    return full_name or None


def _employee_from_shift(shift: dict, employees_map: dict) -> tuple[str | None, str]:
    for key in ["opened_by_employee", "closed_by_employee", "employee"]:
        value = shift.get(key)
        if isinstance(value, dict):
            employee_id = value.get("id") or value.get("employee_id")
            employee_name = _name_from_employee_obj(value)
            if employee_id or employee_name:
                return employee_id, employee_name or employees_map.get(employee_id, "Sin asignar")
        elif isinstance(value, str) and value:
            return value, employees_map.get(value, "Sin asignar")

    employee_id = _first_present(shift, [
        "employee_id",
        "opened_by_employee_id",
        "closed_by_employee_id",
        "cashier_id",
    ])
    return employee_id, employees_map.get(employee_id, "Sin asignar")


def _normalizar_shift(shift: dict, employees_map: dict) -> dict:
    opened_at = _first_present(shift, ["opened_at", "opening_time", "open_time", "created_at"])
    closed_at = _first_present(shift, ["closed_at", "closing_time", "close_time", "updated_at"])
    opened_dt = _parse_dt(opened_at)
    closed_dt = _parse_dt(closed_at)
    hours = None
    if opened_dt and closed_dt:
        hours = round((closed_dt - opened_dt).total_seconds() / 3600, 2)

    employee_id, employee_name = _employee_from_shift(shift, employees_map)
    pos_id = _first_present(shift, ["pos_device_id", "store_id"])

    return {
        "shift_id": _first_present(shift, ["id", "shift_id"]),
        "employee_id": employee_id,
        "employee_name": employee_name,
        "pos_id": pos_id,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "hours": hours,
        "raw_keys": sorted(list(shift.keys())),
    }


@router.get("/turnos-loyverse")
async def turnos_loyverse(
    desde: date = Query(...),
    hasta: date = Query(...),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    """
    Consulta turnos de caja cerrados de Loyverse para validar si sirven como base
    de calculo de horas trabajadas. No modifica facturacion ni DB local.
    """
    _require_admin_key(x_admin_key)
    result = await _fetch_loyverse_shifts(desde, hasta)
    if result.get("error"):
        return JSONResponse(status_code=502, content={
            "ok": False,
            "source": "loyverse_shifts",
            "error": result["error"],
        })

    employees_map = await get_employees()
    normalized = [_normalizar_shift(s, employees_map) for s in result["shifts"]]
    by_employee = defaultdict(lambda: {"employee_id": None, "employee_name": "", "shifts": 0, "hours": 0})
    for item in normalized:
        key = item["employee_id"] or item["employee_name"] or "sin_asignar"
        by_employee[key]["employee_id"] = item["employee_id"]
        by_employee[key]["employee_name"] = item["employee_name"]
        by_employee[key]["shifts"] += 1
        by_employee[key]["hours"] = round(by_employee[key]["hours"] + (item["hours"] or 0), 2)

    return {
        "ok": True,
        "source": "loyverse_shifts",
        "attempt": result["attempt"],
        "raw_count": result.get("raw_count", len(result["shifts"])),
        "filtered_locally": result.get("filtered_locally", False),
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "total_shifts": len(normalized),
        "sample_raw_keys": normalized[0]["raw_keys"] if normalized else [],
        "turnos": normalized,
        "por_empleado": sorted(by_employee.values(), key=lambda x: x["employee_name"]),
    }


@router.get("/sueldos")
async def sueldos_admin(
    desde: date = Query(...),
    hasta: date = Query(...),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    _require_admin_key(x_admin_key)
    result = await _fetch_loyverse_shifts(desde, hasta)
    if result.get("error"):
        return JSONResponse(status_code=502, content={
            "ok": False,
            "source": "loyverse_shifts",
            "error": result["error"],
        })

    employees_map = await get_employees()
    sueldos_db = _load_sueldos_db()
    normalized = [_normalizar_shift(s, employees_map) for s in result["shifts"]]
    shifts = [_apply_salary_data(s, sueldos_db) for s in normalized]

    days = defaultdict(list)
    for shift in sorted(shifts, key=lambda s: (s.get("date", ""), s.get("opened_time", ""))):
        days[shift.get("date", "")].append(shift)

    return {
        "ok": True,
        "source": "loyverse_shifts",
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "employee_names": sueldos_db["employee_names"],
        "hourly_rates": sueldos_db["hourly_rates"],
        "turnos": shifts,
        "days": dict(days),
        "resumen": _summarize_sueldos(shifts, sueldos_db),
    }


@router.post("/sueldos/salario")
async def guardar_salario(
    req: SalaryRequest,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    _require_admin_key(x_admin_key)
    if req.hourly_rate < 0:
        raise HTTPException(status_code=400, detail="El salario por hora no puede ser negativo.")
    db = _load_sueldos_db()
    db["hourly_rates"][req.employee_id] = req.hourly_rate
    if req.employee_id in EMPLOYEE_NAME_MAP:
        db["employee_names"][req.employee_id] = EMPLOYEE_NAME_MAP[req.employee_id]
    _save_sueldos_db(db)
    return {"ok": True, "hourly_rates": db["hourly_rates"]}


@router.post("/sueldos/override")
async def guardar_override_turno(
    req: ShiftOverrideRequest,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    _require_admin_key(x_admin_key)
    if not req.shift_id.strip():
        raise HTTPException(status_code=400, detail="Falta shift_id.")
    if not req.employee_id.strip():
        raise HTTPException(status_code=400, detail="Falta employee_id.")
    db = _load_sueldos_db()
    employee_name = req.employee_name or db["employee_names"].get(req.employee_id) or EMPLOYEE_NAME_MAP.get(req.employee_id) or "Sin asignar"
    db["shift_overrides"][req.shift_id] = {
        "employee_id": req.employee_id,
        "employee_name": employee_name,
        "note": req.note or "",
        "updated_at": datetime.now(timezone(timedelta(hours=-3))).isoformat(),
    }
    _save_sueldos_db(db)
    return {"ok": True, "override": db["shift_overrides"][req.shift_id]}


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
