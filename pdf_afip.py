import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color, black
from io import BytesIO
import qrcode

# -----------------------------
# PALETA DE COLORES / BRANDING
# -----------------------------
COLOR_PRIMARIO = Color(0.027, 0.133, 0.282)   # Azul oscuro
COLOR_SEC1 = Color(0.976, 0.592, 0.0)         # Naranja
COLOR_SEC2 = Color(0.113, 0.584, 0.760)       # Celeste
COLOR_SEC3 = Color(0.937, 0.078, 0.463)       # Rosa
COLOR_SEC4 = Color(0.875, 0.863, 0.0)         # Amarillo

# -----------------------------
# DATOS FIJOS DEL CONTRIBUYENTE
# (estructura AFIP)
# -----------------------------
COND_IVA = "MONOTRIBUTO"
INGRESOS_BRUTOS = "20-39157186-5"
INICIO_ACT = "01/01/2020"

# Ruta del logo ya probado en Render
LOGO_PATH = "static/logo_fixed.png"


def _formatear_cuit_display(cuit_str: str) -> str:
    """
    Toma '20391571865' y devuelve '20-39157186-5' si tiene 11 dígitos.
    Si viene con otro formato, lo devuelve tal cual.
    """
    solo_digitos = "".join(ch for ch in str(cuit_str) if ch.isdigit())
    if len(solo_digitos) == 11:
        return f"{solo_digitos[0:2]}-{solo_digitos[2:10]}-{solo_digitos[10]}"
    return str(cuit_str)


def _formatear_fecha_cae_vto(cae_vto: str) -> str:
    """
    Convierte '20251209' -> '09/12/2025'.
    Si viene en otro formato, lo devuelve como está.
    """
    s = str(cae_vto or "")
    if len(s) == 8 and s.isdigit():
        return f"{s[6:8]}/{s[4:6]}/{s[0:4]}"
    return s


def generar_qr_afip(cuit, pto_vta, cbte_nro, cae, cae_vto):
    """
    Genera el QR AFIP oficial.
    """
    data = (
        f"https://www.afip.gob.ar/fe/qr/?"
        f"p={{"
        f"\"ver\":1,"
        f"\"fecha\":\"{datetime.now().strftime('%Y-%m-%d')}\","
        f"\"cuit\":{cuit},"
        f"\"ptoVta\":{pto_vta},"
        f"\"tipoCbte\":11,"
        f"\"nroCmp\":{cbte_nro},"
        f"\"importe\":0,"
        f"\"moneda\":\"PES\","
        f"\"ctz\":1,"
        f"\"tipoDocRec\":96,"
        f"\"nroDocRec\":0,"
        f"\"tipoCodAut\":\"E\","
        f"\"codAut\":{cae}"
        f"}}"
    )
    qr_img = qrcode.make(data)
    buf = BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    return buf


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
    cliente_dni: str,
    items: list,
    total: float,
):
    """
    Genera el PDF de Factura C con:
    - Header con branding
    - Bloque AFIP / datos del emisor
    - Datos del cliente
    - Detalle de ítems
    - Total
    - CAE + Vto. CAE + QR AFIP
    """

    folder = "generated_pdfs"
    os.makedirs(folder, exist_ok=True)
    filename = f"{folder}/factura_C_{pto_vta:04d}_{cbte_nro:08d}.pdf"

    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    # -------------------------------------
    # HEADER SUPERIOR (BARRA AZUL + TEXTO)
    # -------------------------------------
    header_h = 70
    c.setFillColor(COLOR_PRIMARIO)
    c.rect(0, height - header_h, width, header_h, fill=True, stroke=False)

    c.setFillColor("white")
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - header_h + 25, "FACTURA C")

    # -------------------------------------
    # BLOQUE EMISOR (LOGO + DATOS COMERCIO)
    # -------------------------------------
    top_y = height - header_h - 20
    left_margin = 40

    # Logo pequeño alineado a la izquierda dentro del bloque de comercio
    logo_width = 70
    logo_height = 70
    logo_y = top_y - logo_height

    if os.path.exists(LOGO_PATH):
        try:
            img_logo = ImageReader(LOGO_PATH)
            c.drawImage(
                img_logo,
                left_margin,
                logo_y,
                width=logo_width,
                height=logo_height,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception as e:
            print("Error dibujando logo:", e)
    else:
        print("Logo no encontrado en:", LOGO_PATH)

    # Datos del comercio a la derecha del logo
    text_x = left_margin + logo_width + 10
    y = top_y

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(text_x, y, razon_social.upper())
    y -= 14

    c.setFont("Helvetica", 10)
    c.drawString(text_x, y, domicilio)
    y -= 12

    cuit_display = _formatear_cuit_display(cuit)
    c.drawString(text_x, y, f"CUIT: {cuit_display}")
    y -= 12

    c.drawString(text_x, y, f"Condición frente al IVA: {COND_IVA}")
    y -= 12

    c.drawString(text_x, y, f"Ingresos Brutos: {INGRESOS_BRUTOS}")
    y -= 12

    c.drawString(text_x, y, f"Fecha de inicio de actividades: {INICIO_ACT}")

    # -------------------------------------
    # BLOQUE DATOS DEL COMPROBANTE (ESTILO AFIP)
    # -------------------------------------
    box_w = 210
    box_h = 75
    box_x = width - left_margin - box_w
    box_y = top_y - 5  # un poco por debajo del header

    # Marco
    c.rect(box_x, box_y - box_h, box_w, box_h, stroke=1, fill=0)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(box_x + 10, box_y - 15, f"Punto de Venta: {pto_vta:04d}")
    c.drawString(box_x + 10, box_y - 30, f"Comp. N°: {cbte_nro:08d}")

    c.setFont("Helvetica", 10)
    c.drawString(box_x + 10, box_y - 45, f"Fecha de emisión: {fecha}")
    c.drawString(box_x + 10, box_y - 60, "Tipo: FACTURA C (Cod. 11)")

    # -------------------------------------
    # SEPARADOR
    # -------------------------------------
    sep_y = logo_y - 20
    c.setStrokeColor(COLOR_SEC1)
    c.line(left_margin, sep_y, width - left_margin, sep_y)

    # -------------------------------------
    # DATOS DEL CLIENTE
    # -------------------------------------
    y = sep_y - 20
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(black)
    c.drawString(left_margin, y, "Datos del Cliente")
    y -= 15

    c.setFont("Helvetica", 10)
    nombre_cliente = cliente_nombre or "Consumidor Final"
    c.drawString(left_margin, y, f"Nombre: {nombre_cliente}")
    y -= 15

    if cliente_dni:
        c.drawString(left_margin, y, f"DNI / Doc.: {cliente_dni}")
    else:
        c.drawString(left_margin, y, "DNI / Doc.: Consumidor Final")

    # -------------------------------------
    # DETALLE DE ÍTEMS
    # -------------------------------------
    y_items_start = y - 35
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left_margin, y_items_start, "Descripción")
    c.drawString(300, y_items_start, "Cant.")
    c.drawString(360, y_items_start, "Precio")
    c.drawString(440, y_items_start, "Subtotal")

    y = y_items_start - 10
    c.setStrokeColor(COLOR_SEC1)
    c.line(left_margin, y, width - left_margin, y)
    y -= 18

    c.setFont("Helvetica", 10)
    for it in items:
        desc = str(it["descripcion"])
        cant = float(it["cantidad"])
        precio = float(it["precio"])
        subtotal = cant * precio

        c.drawString(left_margin, y, desc[:60])
        c.drawRightString(330, y, f"{cant:.2f}")
        c.drawRightString(420, y, f"${precio:.2f}")
        c.drawRightString(width - left_margin, y, f"${subtotal:.2f}")

        y -= 16
        if y < 150:  # si se va muy abajo, saltar de página (simple)
            c.showPage()
            c = canvas.Canvas(filename, pagesize=A4)  # para este caso simple, no soportamos multi-página real
            width, height = A4
            y = height - 100

    # -------------------------------------
    # TOTAL
    # -------------------------------------
    y -= 15
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(COLOR_SEC2)
    c.drawString(left_margin, y, f"TOTAL: ${total:.2f}")
    c.setFillColor(black)

    # -------------------------------------
    # CAE + VTO CAE + QR (ESTILO AFIP)
    # -------------------------------------
    cae_texto = f"CAE N°: {cae}"
    cae_vto_fmt = _formatear_fecha_cae_vto(cae_vto)
    vto_texto = f"Vencimiento CAE: {cae_vto_fmt}"

    qr_size = 110
    qr_x = width - left_margin - qr_size
    qr_y = 40

    # Texto CAE a la izquierda del QR
    text_cae_x = left_margin
    text_cae_y = qr_y + qr_size - 10

    c.setFont("Helvetica-Bold", 10)
    c.drawString(text_cae_x, text_cae_y, cae_texto)
    c.setFont("Helvetica", 10)
    c.drawString(text_cae_x, text_cae_y - 15, vto_texto)
    c.drawString(text_cae_x, text_cae_y - 30, "Comprobante Autorizado por AFIP")

    # QR
    try:
        qr_buf = generar_qr_afip(cuit, pto_vta, cbte_nro, cae, cae_vto)
        qr_img = ImageReader(qr_buf)
        c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size)
    except Exception as e:
        print("Error generando QR:", e)

    # -------------------------------------
    # FINAL
    # -------------------------------------
    c.showPage()
    c.save()

    return filename
