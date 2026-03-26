"""
arqueo_api.py — Endpoints para arqueo de caja, retiros del propietario y movimientos de empleados.

Rutas:
  GET  /api/arqueo/estado          — turno abierto actual (o null)
  POST /api/arqueo/abrir           — abre un nuevo turno
  POST /api/arqueo/cerrar          — cierra el turno (con o sin diferencia)
  GET  /api/arqueo/historial       — últimos 30 arqueos cerrados
  POST /api/retiro                 — retiro del propietario (solo admin)
  GET  /api/retiros                — lista todos los retiros del propietario
  POST /api/arqueo/movimiento      — egreso o ingreso manual registrado por el empleado del turno
  GET  /api/arqueo/movimientos     — movimientos del turno actual
"""

import os
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client

logger = logging.getLogger(__name__)
router = APIRouter()

ARGENTINA = timezone(timedelta(hours=-3))
OWNER_EMAIL = "joaquin.vegli@gmail.com"
ARQUEOS_DB_PATH = "db/arqueos_db.json"
SUPABASE_BUCKET = "facturas"

LOYVERSE_TOKEN = os.getenv("LOYVERSE_TOKEN", "")
LOYVERSE_BASE = "https://api.loyverse.com/v1.0"
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")


# ══════════════════════════════════════════════
# Supabase helpers
# ══════════════════════════════════════════════

def _get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY")
    return create_client(url, key)


def _descargar_arqueos_db() -> dict:
    try:
        supabase = _get_supabase()
        url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(ARQUEOS_DB_PATH)
        url_sin_cache = f"{url}?t={int(time.time())}"
        r = httpx.get(url_sin_cache, timeout=15, follow_redirects=True)
        if r.status_code in (400, 404):
            return {"turno_abierto": None, "arqueos": [], "retiros": [], "movimientos": []}
        r.raise_for_status()
        content = r.text.strip()
        if not content:
            return {"turno_abierto": None, "arqueos": [], "retiros": [], "movimientos": []}
        data = json.loads(content)
        # Migración: asegurar que exista la clave movimientos
        if "movimientos" not in data:
            data["movimientos"] = []
        return data
    except json.JSONDecodeError:
        return {"turno_abierto": None, "arqueos": [], "retiros": [], "movimientos": []}
    except Exception as e:
        logger.error(f"Error descargando arqueos_db: {e}")
        return {"turno_abierto": None, "arqueos": [], "retiros": [], "movimientos": []}


def _subir_arqueos_db(data: dict) -> None:
    try:
        supabase = _get_supabase()
        json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            path=ARQUEOS_DB_PATH,
            file=json_bytes,
            file_options={"content-type": "application/json", "upsert": "true"},
        )
    except Exception as e:
        logger.error(f"Error subiendo arqueos_db: {e}")
        raise


# ══════════════════════════════════════════════
# Modelos
# ══════════════════════════════════════════════

class AbrirTurnoRequest(BaseModel):
    empleado: str
    efectivo_inicial: float


class CerrarTurnoRequest(BaseModel):
    efectivo_contado: float
    nota: Optional[str] = ""


class RetiroRequest(BaseModel):
    monto: float
    motivo: str


class MovimientoRequest(BaseModel):
    tipo: Literal["egreso", "ingreso"]
    monto: float
    detalle: str


# ══════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════

def _now_arg() -> str:
    return datetime.now(ARGENTINA).isoformat()


async def _ventas_efectivo_desde(desde_iso: str) -> list[dict]:
    """Trae todos los receipts con pagos en efectivo (CASH) desde `desde_iso`. Incluye SALE y REFUND."""
    headers = {"Authorization": f"Bearer {LOYVERSE_TOKEN}"}
    try:
        dt = datetime.fromisoformat(desde_iso)
        desde_utc = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        desde_utc = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
    hasta_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    resultados = []
    cursor = None
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params = {"created_at_min": desde_utc, "created_at_max": hasta_utc, "limit": 250}
            if cursor:
                params["cursor"] = cursor
            resp = await client.get(f"{LOYVERSE_BASE}/receipts", headers=headers, params=params)
            if resp.status_code != 200:
                logger.error(f"Loyverse error {resp.status_code}: {resp.text}")
                break
            body = resp.json()
            for r in body.get("receipts", []):
                payments = r.get("payments", [])
                cash_total = sum(p.get("money_amount", 0) for p in payments if p.get("type") == "CASH")
                if cash_total == 0:
                    continue
                resultados.append({
                    "receipt_id": r.get("receipt_id") or r.get("receipt_number", ""),
                    "receipt_number": r.get("receipt_number", ""),
                    "tipo": r.get("receipt_type", "SALE"),
                    "total_efectivo": cash_total,
                    "total": r.get("total_money", 0),
                    "fecha": r.get("created_at", ""),
                })
            cursor = body.get("cursor")
            if not cursor or len(body.get("receipts", [])) < 250:
                break
    return resultados


async def _ventas_no_efectivo_desde(desde_iso: str) -> list[dict]:
    """Trae ventas SALE del turno con al menos un pago NO en efectivo (candidatas a explicar diferencia)."""
    headers = {"Authorization": f"Bearer {LOYVERSE_TOKEN}"}
    try:
        dt = datetime.fromisoformat(desde_iso)
        desde_utc = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        desde_utc = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
    hasta_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    resultados = []
    cursor = None
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params = {"created_at_min": desde_utc, "created_at_max": hasta_utc, "limit": 250}
            if cursor:
                params["cursor"] = cursor
            resp = await client.get(f"{LOYVERSE_BASE}/receipts", headers=headers, params=params)
            if resp.status_code != 200:
                break
            body = resp.json()
            for r in body.get("receipts", []):
                if r.get("receipt_type") != "SALE":
                    continue
                payments = r.get("payments", [])
                non_cash = [p for p in payments if p.get("type") != "CASH"]
                if not non_cash:
                    continue
                non_cash_total = sum(p.get("money_amount", 0) for p in non_cash)
                resultados.append({
                    "receipt_id": r.get("receipt_id") or r.get("receipt_number", ""),
                    "receipt_number": r.get("receipt_number", ""),
                    "total": r.get("total_money", 0),
                    "total_no_efectivo": non_cash_total,
                    "fecha": r.get("created_at", ""),
                    "metodos": list({p.get("type", "") for p in payments}),
                })
            cursor = body.get("cursor")
            if not cursor or len(body.get("receipts", [])) < 250:
                break
    return resultados


def _calcular_resumen(
    efectivo_inicial: float,
    ventas: list[dict],
    retiros: list[dict],
    movimientos: list[dict],
) -> dict:
    ingresos_ventas = sum(v["total_efectivo"] for v in ventas if v["tipo"] == "SALE")
    egresos_reembolsos = sum(v["total_efectivo"] for v in ventas if v["tipo"] == "REFUND")
    egresos_retiros = sum(r["monto"] for r in retiros)
    ingresos_manuales = sum(m["monto"] for m in movimientos if m["tipo"] == "ingreso")
    egresos_manuales = sum(m["monto"] for m in movimientos if m["tipo"] == "egreso")

    esperado = (
        efectivo_inicial
        + ingresos_ventas
        - egresos_reembolsos
        - egresos_retiros
        + ingresos_manuales
        - egresos_manuales
    )
    return {
        "efectivo_inicial": efectivo_inicial,
        "ingresos_efectivo": round(ingresos_ventas, 2),
        "egresos_reembolsos": round(egresos_reembolsos, 2),
        "egresos_retiros": round(egresos_retiros, 2),
        "ingresos_manuales": round(ingresos_manuales, 2),
        "egresos_manuales": round(egresos_manuales, 2),
        "esperado": round(esperado, 2),
    }


def _buscar_combinaciones(diferencia: float, ventas_no_efectivo: list[dict], tolerancia: float = 1.0) -> list[dict]:
    objetivo = abs(diferencia)
    candidatos = []
    elegibles = sorted(ventas_no_efectivo, key=lambda v: abs(v["total_no_efectivo"] - objetivo))

    def buscar(idx, acum, combo):
        if acum > 0 and abs(acum - objetivo) <= tolerancia:
            candidatos.append(list(combo))
            return
        if idx >= len(elegibles) or len(combo) >= 3 or acum > objetivo + tolerancia:
            return
        v = elegibles[idx]
        buscar(idx + 1, acum + v["total_no_efectivo"], combo + [v])
        buscar(idx + 1, acum, combo)

    buscar(0, 0.0, [])
    seen = set()
    result = []
    for combo in candidatos:
        key = tuple(sorted(v["receipt_id"] for v in combo))
        if key not in seen:
            seen.add(key)
            result.append({
                "ventas": combo,
                "total": round(sum(v["total_no_efectivo"] for v in combo), 2),
            })
        if len(result) >= 5:
            break
    return result


async def _enviar_mail_diferencia(empleado: str, diferencia: float, resumen: dict, turno_id: str):
    signo = "SOBRANTE" if diferencia > 0 else "FALTANTE"
    monto_fmt = f"${abs(diferencia):,.2f}"
    asunto = f"⚠️ Arqueo con diferencia — {empleado} — {signo} {monto_fmt}"
    cuerpo = f"""Arqueo de caja cerrado con diferencia.

Empleado: {empleado}
Turno ID: {turno_id}
Fecha cierre: {_now_arg()[:19].replace("T", " ")}

── Resumen ──────────────────────────────
Efectivo inicial:      ${resumen['efectivo_inicial']:,.2f}
Ingresos efectivo:     ${resumen['ingresos_efectivo']:,.2f}
Egresos reembolsos:    ${resumen['egresos_reembolsos']:,.2f}
Egresos retiros:       ${resumen['egresos_retiros']:,.2f}
Ingresos manuales:     ${resumen['ingresos_manuales']:,.2f}
Egresos manuales:      ${resumen['egresos_manuales']:,.2f}
─────────────────────────────────────────
Esperado en caja:      ${resumen['esperado']:,.2f}
Contado por empleado:  ${resumen.get('contado', 0):,.2f}
─────────────────────────────────────────
DIFERENCIA ({signo}): {monto_fmt}

Revisá los comprobantes sugeridos en la app para identificar el origen de la diferencia."""

    payload = {
        "sender": {"name": "Top Fundas Sistema", "email": "no-reply@topfundas.com"},
        "to": [{"email": OWNER_EMAIL, "name": "Joaquín Vegli"}],
        "subject": asunto,
        "textContent": cuerpo,
    }
    headers_brevo = {"api-key": BREVO_API_KEY, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post("https://api.brevo.com/v3/smtp/email", json=payload, headers=headers_brevo)
            if resp.status_code not in (200, 201):
                logger.error(f"Brevo error {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Error enviando mail arqueo: {e}")


# ══════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════

@router.get("/api/arqueo/estado")
async def get_estado_arqueo():
    """Devuelve el turno abierto. Si no hay, sugiere el efectivo del último cierre."""
    db = _descargar_arqueos_db()
    turno = db.get("turno_abierto")
    if not turno:
        arqueos = db.get("arqueos", [])
        efectivo_sugerido = None
        if arqueos:
            ultimo = sorted(arqueos, key=lambda a: a.get("fecha_cierre", ""))[-1]
            efectivo_sugerido = ultimo.get("efectivo_contado")
        return {"turno_abierto": None, "efectivo_inicial_sugerido": efectivo_sugerido}
    return {"turno_abierto": turno}


@router.post("/api/arqueo/abrir")
async def abrir_turno(req: AbrirTurnoRequest):
    """Abre un nuevo turno de caja."""
    if not req.empleado.strip():
        raise HTTPException(status_code=400, detail="El nombre del empleado es obligatorio.")
    db = _descargar_arqueos_db()
    if db.get("turno_abierto"):
        raise HTTPException(status_code=400, detail="Ya hay un turno abierto. Cerralo primero.")
    turno_id = f"T-{datetime.now(ARGENTINA).strftime('%Y%m%d%H%M%S')}"
    turno = {
        "turno_id": turno_id,
        "empleado": req.empleado.strip(),
        "efectivo_inicial": req.efectivo_inicial,
        "fecha_apertura": _now_arg(),
    }
    db["turno_abierto"] = turno
    _subir_arqueos_db(db)
    return {"ok": True, "turno": turno}


@router.post("/api/arqueo/movimiento")
async def registrar_movimiento(req: MovimientoRequest):
    """
    Registra un egreso o ingreso manual durante el turno abierto.
    El nombre del empleado se toma del turno abierto automáticamente.
    """
    if req.monto <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")
    if not req.detalle.strip():
        raise HTTPException(status_code=400, detail="El detalle es obligatorio.")

    db = _descargar_arqueos_db()
    turno = db.get("turno_abierto")
    if not turno:
        raise HTTPException(status_code=400, detail="No hay turno abierto. Abrí un turno primero.")

    movimiento = {
        "mov_id": f"M-{datetime.now(ARGENTINA).strftime('%Y%m%d%H%M%S')}",
        "tipo": req.tipo,                    # "egreso" | "ingreso"
        "monto": req.monto,
        "detalle": req.detalle.strip(),
        "empleado": turno["empleado"],       # tomado del turno abierto
        "turno_id": turno["turno_id"],
        "fecha": _now_arg(),
    }
    db["movimientos"].append(movimiento)
    _subir_arqueos_db(db)
    return {"ok": True, "movimiento": movimiento}


@router.get("/api/arqueo/movimientos")
async def get_movimientos_turno():
    """Devuelve los movimientos del turno actualmente abierto."""
    db = _descargar_arqueos_db()
    turno = db.get("turno_abierto")
    todos = db.get("movimientos", [])
    if not turno:
        return {"movimientos": [], "turno_abierto": False}
    turno_id = turno["turno_id"]
    del_turno = [m for m in todos if m.get("turno_id") == turno_id]
    return {"movimientos": del_turno, "turno_abierto": True}


@router.post("/api/arqueo/cerrar")
async def cerrar_turno(req: CerrarTurnoRequest):
    """
    Cierra el turno abierto.
    Calcula diferencia incluyendo movimientos manuales, sugiere comprobantes, envía mail si corresponde.
    """
    db = _descargar_arqueos_db()
    turno = db.get("turno_abierto")
    if not turno:
        raise HTTPException(status_code=400, detail="No hay turno abierto.")

    desde_iso = turno["fecha_apertura"]
    empleado = turno["empleado"]
    efectivo_inicial = turno["efectivo_inicial"]
    turno_id = turno["turno_id"]

    # Ventas en efectivo del turno desde Loyverse
    ventas_efectivo = await _ventas_efectivo_desde(desde_iso)

    # Retiros del propietario durante este turno
    retiros_turno = [r for r in db.get("retiros", []) if r.get("fecha", "") >= desde_iso]

    # Movimientos manuales del empleado durante este turno
    movimientos_turno = [m for m in db.get("movimientos", []) if m.get("turno_id") == turno_id]

    # Resumen y diferencia
    resumen = _calcular_resumen(efectivo_inicial, ventas_efectivo, retiros_turno, movimientos_turno)
    resumen["contado"] = req.efectivo_contado
    diferencia = round(req.efectivo_contado - resumen["esperado"], 2)
    resumen["diferencia"] = diferencia

    # Comprobantes candidatos si hay diferencia
    combinaciones_sugeridas = []
    if abs(diferencia) > 0.5:
        ventas_no_ef = await _ventas_no_efectivo_desde(desde_iso)
        combinaciones_sugeridas = _buscar_combinaciones(diferencia, ventas_no_ef)

    # Guardar arqueo cerrado
    arqueo_cerrado = {
        "turno_id": turno_id,
        "empleado": empleado,
        "fecha_apertura": turno["fecha_apertura"],
        "fecha_cierre": _now_arg(),
        "efectivo_inicial": efectivo_inicial,
        "efectivo_contado": req.efectivo_contado,
        "nota": req.nota or "",
        "resumen": resumen,
        "diferencia": diferencia,
        "retiros_turno": retiros_turno,
        "movimientos_turno": movimientos_turno,
        "ventas_efectivo_count": len([v for v in ventas_efectivo if v["tipo"] == "SALE"]),
        "reembolsos_efectivo_count": len([v for v in ventas_efectivo if v["tipo"] == "REFUND"]),
    }

    if "arqueos" not in db:
        db["arqueos"] = []
    db["arqueos"].append(arqueo_cerrado)
    db["turno_abierto"] = None
    _subir_arqueos_db(db)

    if abs(diferencia) > 0.5:
        await _enviar_mail_diferencia(empleado, diferencia, resumen, turno_id)

    return {
        "ok": True,
        "arqueo": arqueo_cerrado,
        "combinaciones_sugeridas": combinaciones_sugeridas,
        "hay_diferencia": abs(diferencia) > 0.5,
    }


@router.get("/api/arqueo/historial")
async def get_historial_arqueos():
    db = _descargar_arqueos_db()
    arqueos = db.get("arqueos", [])
    return {"arqueos": sorted(arqueos, key=lambda a: a.get("fecha_cierre", ""), reverse=True)[:30]}


@router.post("/api/retiro")
async def registrar_retiro(req: RetiroRequest):
    """Registra un retiro del propietario. Validación de admin en el frontend."""
    if req.monto <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")
    db = _descargar_arqueos_db()
    retiro = {
        "retiro_id": f"R-{datetime.now(ARGENTINA).strftime('%Y%m%d%H%M%S')}",
        "monto": req.monto,
        "motivo": req.motivo.strip(),
        "fecha": _now_arg(),
    }
    if "retiros" not in db:
        db["retiros"] = []
    db["retiros"].append(retiro)
    _subir_arqueos_db(db)
    return {"ok": True, "retiro": retiro}


@router.get("/api/retiros")
async def get_retiros():
    db = _descargar_arqueos_db()
    retiros = db.get("retiros", [])
    return {"retiros": sorted(retiros, key=lambda r: r.get("fecha", ""), reverse=True)}
