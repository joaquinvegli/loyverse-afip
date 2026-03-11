import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color, black
from io import BytesIO
import qrcode
import base64
import json

# -----------------------------
# PALETA DE COLORES / BRANDING
# -----------------------------
COLOR_PRIMARIO = Color(0.027, 0.133, 0.282)
COLOR_SEC1 = Color(0.976, 0.592, 0.0)
COLOR_SEC2 = Color(0.113, 0.584, 0.760)
COLOR_SEC3 = Color(0.937, 0.078, 0.463)
COLOR_SEC4 = Color(0.875, 0.863, 0.0)

# -----------------------------
# DATOS FIJOS DEL CONTRIBUYENTE
# -----------------------------
COND_IVA = "MONOTRIBUTO"
INGRESOS_BRUTOS = "20-39157186-5"
INICIO_ACT = "01/01/2020"

# -----------------------------
# LOGO
# -----------------------------
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(_BASE_DIR, "static", "logo_fixed.png")


def _formatear_cuit_display(cuit_str: str) -> str:
    solo = "".join(ch for ch in str(cuit_str) if ch.isdigit())
    if len(solo) == 11:
        return f"{solo[0:2]}-{solo[2:10]}-{solo[10]}"
    return str(cuit_str)


def _formatear_fecha_cae_vto(cae_vto: str) -> str:
    s = str(cae_vto or "")
    if len(s) == 8 and s.isdigit():
        return f"{s[6:8]}/{s[4:6]}/{s[0:4]}"
    return s


def _wrap_text(text, max_chars=45):
    palabras = text.split(" ")
    lineas = []
    actual = ""
    for p in palabras:
        if len(actual) + len(p) + 1 <= max_chars:
            actual += (" " if actual else "") + p
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


# ============================================
# QR OFICIAL AFIP (RG 4892)
# ============================================
def generar_qr_afip(cuit, pto_vta, cbte_nro, cae, cae_vto, fecha_cbte, total, doc_tipo, doc_nro):
    try:
        fecha_iso = datetime.strptime(fecha_cbte, "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        fecha_iso = datetime.now().strftime("%Y-%m-%d")

    payload = {
        "ver": 1,
        "fecha": fecha_iso,
        "cuit": int("".join(ch for ch in str(cuit) if ch.isdigit())),
        "ptoVta": int(pto_vta),
        "tipoCmp": 11,
        "nroCmp": int(cbte_nro),
        "importe": float(total),
        "moneda": "PES",
        "ctz": 1,
        "tipoDocRec": int(doc_tipo),
        "nroDocRec": int(doc_nro),
        "tipoCodAut": "E",
        "codAut": int(cae),
    }

    payload_str = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_str.encode("utf-8")).decode("utf-8")
    url = f"https://www.afip.gob.ar/fe/qr/?p={payload_b64}"

    qr_img = qrcode.make(url)
    buf = BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _resolver_doc(cliente_dni: str | None, cliente_cuit: str | None) -> tuple:
    """
    Retorna (doc_tipo, doc_nro, doc_label) para usar en PDF y QR.
    - CUIT/CUIL: tipo 80
    - DNI: tipo 96
    - Sin dato: tipo 99, nro 0
    """
    if cliente_cuit:
        solo = "".join(c for c in str(cliente_cuit) if c.isdigit())
        if solo:
            return 80, int(solo), f"CUIT/CUIL: {_formatear_cuit_display(solo)}"

    if cliente_dni:
        solo = "".join(c for c in str(cliente_dni) if c.isdigit())
        if solo:
            return 96, int(solo), f"DNI: {solo}"

    return 99, 0, "Consumidor Final"


def generar_pdf_factura_c(
    razon_social: str,
    domicilio: str,
    cuit: str,
    pto_vta: int,
    cbte_nro: int,
    fecha: str,
    cae: str,
    cae_vto: str,
    cliente_nombre: str,
    cliente_dni: str | None,
    cliente_cuit: str | None = None,
    items: list = [],
    total: float = 0.0,
):
    folder = "generated_pdfs"
    os.makedirs(folder, exist_ok=True)
    filename = f"{folder}/factura_C_{pto_vta:04d}_{cbte_nro:08d}.pdf"

    doc_tipo, doc_nro, doc_label = _resolver_doc(cliente_dni, cliente_cuit)

    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    # -----------------------------
    # HEADER
    # -----------------------------
    header_h = 70
    c.setFillColor(COLOR_PRIMARIO)
    c.rect(0, height - header_h, width, header_h, fill=True, stroke=False)

    c.setFillColor("white")
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - header_h + 25, "FACTURA C")

    # -----------------------------
    # BLOQUE EMISOR
    # -----------------------------
    top_y = height - header_h - 20
    left = 40

    logo_w = 70
    logo_h = 70
    logo_y = top_y - logo_h

    if os.path.exists(LOGO_PATH):
        try:
            img = ImageReader(LOGO_PATH)
            c.drawImage(
                img, left, logo_y,
                width=logo_w, height=logo_h,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception as e:
            print("Error dibujando logo:", e)
    else:
        print(f"Logo no encontrado en: {LOGO_PATH}")

    tx = left + logo_w + 10
    y = top_y

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(tx, y, razon_social.upper())
    y -= 14

    c.setFont("Helvetica", 10)
    for linea in _wrap_text(domicilio):
        c.drawString(tx, y, linea)
        y -= 12

    cuit_disp = _formatear_cuit_display(cuit)
    c.drawString(tx, y, f"CUIT: {cuit_disp}")
    y -= 12
    c.drawString(tx, y, f"Condición frente al IVA: {COND_IVA}")
    y -= 12
    c.drawString(tx, y, f"Ingresos Brutos: {INGRESOS_BRUTOS}")
    y -= 12
    c.drawString(tx, y, f"Inicio de actividades: {INICIO_ACT}")

    # -----------------------------
    # CUADRO COMPROBANTE
    # -----------------------------
    box_w = 210
    box_h = 75
    box_x = width - left - box_w
    box_y = top_y

    c.rect(box_x, box_y - box_h, box_w, box_h, stroke=1, fill=0)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(box_x + 10, box_y - 15, f"Punto de Venta: {pto_vta:04d}")
    c.drawString(box_x + 10, box_y - 30, f"Comp. N°: {cbte_nro:08d}")

    c.setFont("Helvetica", 10)
    c.drawString(box_x + 10, box_y - 45, f"Fecha emisión: {fecha}")
    c.drawString(box_x + 10, box_y - 60, "Tipo: FACTURA C (Cod. 11)")

    # -----------------------------
    # SEPARADOR
    # -----------------------------
    sep_y = logo_y - 20
    c.setStrokeColor(COLOR_SEC1)
    c.line(left, sep_y, width - left, sep_y)

    # -----------------------------
    # DATOS CLIENTE
    # -----------------------------
    y = sep_y - 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Datos del Cliente")
    y -= 15

    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Nombre: {cliente_nombre or 'Consumidor Final'}")
    y -= 15
    c.drawString(left, y, doc_label)

    # -----------------------------
    # ÍTEMS
    # -----------------------------
    y_items_start = y - 35
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y_items_start, "Descripción")
    c.drawString(300, y_items_start, "Cant.")
    c.drawString(360, y_items_start, "Precio")
    c.drawString(440, y_items_start, "Subtotal")

    y = y_items_start - 10
    c.setStrokeColor(COLOR_SEC1)
    c.line(left, y, width - left, y)
    y -= 18

    c.setFont("Helvetica", 10)
    for it in items:
        desc = str(it["descripcion"])
        cant = float(it["cantidad"])
        precio = float(it["precio"])
        subtotal = cant * precio

        c.drawString(left, y, desc[:60])
        c.drawRightString(330, y, f"{cant:.2f}")
        c.drawRightString(420, y, f"${precio:.2f}")
        c.drawRightString(width - left, y, f"${subtotal:.2f}")
        y -= 16

    # -----------------------------
    # TOTAL
    # -----------------------------
    y -= 15
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(COLOR_SEC2)
    c.drawString(left, y, f"TOTAL: ${total:.2f}")
    c.setFillColor(black)

    # -----------------------------
    # CAE + QR
    # -----------------------------
    qr_size = 110
    qr_x = width - left - qr_size
    qr_y = 80

    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, qr_y + qr_size - 10, f"CAE Nº: {cae}")
    c.setFont("Helvetica", 10)
    c.drawString(left, qr_y + qr_size - 25, f"Vencimiento CAE: {_formatear_fecha_cae_vto(cae_vto)}")
    c.drawString(left, qr_y + qr_size - 40, "Comprobante autorizado por AFIP")

    try:
        qr_buf = generar_qr_afip(
            cuit=cuit,
            pto_vta=pto_vta,
            cbte_nro=cbte_nro,
            cae=cae,
            cae_vto=cae_vto,
            fecha_cbte=fecha,
            total=total,
            doc_tipo=doc_tipo,
            doc_nro=doc_nro,
        )
        qr_img = ImageReader(qr_buf)
        c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size)
    except Exception as e:
        print("Error generando QR:", e)

    # -----------------------------
    # PIE DE PÁGINA
    # -----------------------------
    footer_y = 30
    c.setFont("Helvetica", 9)
    c.drawCentredString(width/2, footer_y + 25, "Tienda online: www.topfundas.com.ar")
    c.drawCentredString(width/2, footer_y + 12, "Whatsapp: +5492914357809")
    c.drawCentredString(width/2, footer_y, "Instagram: @topfundasbb")
    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(
        width/2, footer_y - 12,
        "Gracias por su compra — comprobante emitido automáticamente por el sistema de facturación de Top Fundas",
    )

    c.showPage()
    c.save()

    return filename
