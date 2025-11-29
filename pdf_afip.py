import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color, black
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.platypus.doctemplate import SimpleDocTemplate
from io import BytesIO
import qrcode


# ============================
# PALETA DE COLORES
# ============================
COLOR_PRIMARIO = Color(0.027, 0.133, 0.282)   # Azul oscuro
COLOR_SEC1 = Color(0.976, 0.592, 0.0)         # Naranja
COLOR_SEC2 = Color(0.113, 0.584, 0.760)       # Celeste


# ============================
# QR AFIP
# ============================
def generar_qr_afip(cuit, pto_vta, cbte_nro, cae, cae_vto):
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


# ============================
# FACTURA C — PDF COMPLETO
# ============================
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

    # Carpeta donde se guardarán los PDF generados
    folder = "generated_pdfs"
    os.makedirs(folder, exist_ok=True)

    filename = f"{folder}/factura_C_{pto_vta:04d}_{cbte_nro:08d}.pdf"

    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4


    # =====================================================
    # ENCABEZADO PRINCIPAL
    # =====================================================
    c.setFillColor(COLOR_PRIMARIO)
    c.rect(0, height - 60, width, 60, fill=True, stroke=False)

    c.setFillColor("white")
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(width/2, height - 40, "FACTURA C")


    # =====================================================
    # BLOQUE SUPERIOR (LOGO + DATOS COMERCIO)
    # =====================================================
    y = height - 100

    # LOGO — Pequeño y alineado a la izquierda
    logo_path = "static/logo_fixed.png"
    if os.path.exists(logo_path):
        try:
            img = ImageReader(logo_path)
            c.drawImage(img, 40, y - 60, width=70, preserveAspectRatio=True, mask='auto')
        except Exception as e:
            print("Error dibujando logo:", e)


    # TEXTOS PRINCIPALES DEL NEGOCIO
    text_x = 130
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(text_x, y, razon_social)

    c.setFont("Helvetica", 10)

    # WRAP PARA DOMICILIO
    domicilio_style = ParagraphStyle("domStyle", fontName="Helvetica", fontSize=10, leading=12)
    domicilio_p = Paragraph(domicilio, domicilio_style)

    domicilio_width = 300
    domicilio_height = 40
    domicilio_x = text_x
    domicilio_y = y - 14

    domicilio_p.wrapOn(c, domicilio_width, domicilio_height)
    domicilio_p.drawOn(c, domicilio_x, domicilio_y)

    y_data_block_start = domicilio_y - 40

    # Datos fijos
    lines = [
        f"CUIT: {cuit}",
        f"Condición frente al IVA: MONOTRIBUTO",
        f"Ingresos Brutos: {cuit}",
        "Fecha de inicio de actividades: 01/01/2020",
    ]

    y_cursor = y_data_block_start
    for line in lines:
        c.drawString(text_x, y_cursor, line)
        y_cursor -= 14


    # =====================================================
    # CUADRO DERECHA — Datos del comprobante
    # =====================================================
    cuadro_x = 330
    cuadro_y = height - 140
    cuadro_w = 240
    cuadro_h = 95

    c.rect(cuadro_x, cuadro_y - cuadro_h, cuadro_w, cuadro_h)

    c.setFont("Helvetica-Bold", 11)
    c.drawString(cuadro_x + 10, cuadro_y - 20, f"Punto de Venta: {pto_vta:04d}")
    c.drawString(cuadro_x + 10, cuadro_y - 40, f"Comp. Nº: {cbte_nro:08d}")

    c.setFont("Helvetica", 10)
    c.drawString(cuadro_x + 10, cuadro_y - 60, f"Fecha de emisión: {fecha}")
    c.drawString(cuadro_x + 10, cuadro_y - 78, "Tipo: FACTURA C (Cod. 11)")


    # =====================================================
    # SEPARADOR
    # =====================================================
    c.setStrokeColor(COLOR_SEC1)
    c.setLineWidth(2)
    c.line(40, y_cursor - 10, width - 40, y_cursor - 10)

    y = y_cursor - 40


    # =====================================================
    # DATOS DEL CLIENTE
    # =====================================================
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Datos del Cliente")

    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Nombre: {cliente_nombre}")

    y -= 14
    if cliente_dni:
        c.drawString(40, y, f"DNI: {cliente_dni}")
    else:
        c.drawString(40, y, "DNI: Consumidor Final")

    y -= 30


    # =====================================================
    # ITEMS
    # =====================================================
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Descripción")
    c.drawString(300, y, "Cant.")
    c.drawString(360, y, "Precio")
    c.drawString(440, y, "Subtotal")

    y -= 12
    c.setStrokeColor(COLOR_SEC1)
    c.line(40, y, width - 40, y)
    y -= 20

    c.setFont("Helvetica", 10)

    for it in items:
        desc = it["descripcion"]
        cant = it["cantidad"]
        precio = it["precio"]
        subtotal = cant * precio

        c.drawString(40, y, desc[:45])
        c.drawString(300, y, str(cant))
        c.drawString(360, y, f"${precio:.2f}")
        c.drawString(440, y, f"${subtotal:.2f}")

        y -= 16


    # =====================================================
    # TOTAL
    # =====================================================
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(COLOR_SEC2)
    c.drawString(40, y - 10, f"TOTAL: ${total:.2f}")
    c.setFillColor(black)

    # =====================================================
    # CAE + QR estilo AFIP
    # =====================================================
    y_qr = 130

    c.setFont("Helvetica", 10)
    c.drawString(40, y_qr + 80, f"CAE: {cae}")
    c.drawString(40, y_qr + 65, f"Vto. CAE: {cae_vto}")

    try:
        qr_buf = generar_qr_afip(cuit, pto_vta, cbte_nro, cae, cae_vto)
        qr_img = ImageReader(qr_buf)
        c.drawImage(qr_img, width - 160, y_qr, width=120, height=120)
    except Exception as e:
        print("Error generando QR:", e)


    # =====================================================
    # GUARDAR PDF
    # =====================================================
    c.showPage()
    c.save()

    return filename
