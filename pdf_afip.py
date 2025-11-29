import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color, black
from io import BytesIO
import qrcode

# -----------------------------
# PALETA DE COLORES
# -----------------------------
COLOR_PRIMARIO = Color(0.027, 0.133, 0.282)
COLOR_SEC1 = Color(0.976, 0.592, 0.0)
COLOR_SEC2 = Color(0.113, 0.584, 0.760)
COLOR_SEC3 = Color(0.937, 0.078, 0.463)
COLOR_SEC4 = Color(0.875, 0.863, 0.0)


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
    folder = "generated_pdfs"
    os.makedirs(folder, exist_ok=True)

    filename = f"{folder}/factura_C_{pto_vta:04d}_{cbte_nro:08d}.pdf"

    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    # HEADER
    c.setFillColor(COLOR_PRIMARIO)
    c.rect(0, height - 60, width, 60, fill=True, stroke=False)
    c.setFillColor("white")
    c.setFont("Helvetica-Bold", 22)
    c.drawString(200, height - 40, "FACTURA C")

    # LOGO LOCAL — ARCHIVO FIXED
    logo_path = "static/logo_fixed.png"
    if os.path.exists(logo_path):
        try:
            img = ImageReader(logo_path)
            # ←← FIX: bajar logo + height explícito + mask
            c.drawImage(
                img,
                40,
                height - 200,   # ANTES: height - 150 (tapado por header)
                width=120,
                height=120,
                preserveAspectRatio=True,
                mask='auto'
            )
        except Exception as e:
            print("Error dibujando logo:", e)
    else:
        print("Logo no encontrado en:", logo_path)

    # DATOS DEL COMERCIO
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, height - 170, razon_social)

    c.setFont("Helvetica", 10)
    c.drawString(40, height - 185, domicilio)
    c.drawString(40, height - 200, f"CUIT: {cuit}")

    c.drawString(40, height - 215, f"Punto de Venta: {pto_vta:04d}")
    c.drawString(220, height - 215, f"Comprobante Nº: {cbte_nro:08d}")
    c.drawString(40, height - 230, f"Fecha: {fecha}")

    # CLIENTE
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, height - 265, "Datos del Cliente")

    c.setFont("Helvetica", 10)
    c.drawString(40, height - 280, f"Nombre: {cliente_nombre}")

    if cliente_dni:
        c.drawString(40, height - 295, f"DNI: {cliente_dni}")
    else:
        c.drawString(40, height - 295, "DNI: Consumidor Final")

    # ITEMS
    y = height - 335

    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Descripción")
    c.drawString(300, y, "Cant.")
    c.drawString(360, y, "Precio")
    c.drawString(440, y, "Subtotal")

    y -= 10
    c.setStrokeColor(COLOR_SEC1)
    c.line(40, y, width - 40, y)
    y -= 20

    c.setFont("Helvetica", 10)
    for it in items:
        desc = it["descripcion"]
        cant = it["cantidad"]
        precio = it["precio"]
        subtotal = cant * precio

        c.drawString(40, y, desc[:40])
        c.drawString(300, y, str(cant))
        c.drawString(360, y, f"${precio:.2f}")
        c.drawString(440, y, f"${subtotal:.2f}")

        y -= 18

    # TOTAL
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(COLOR_SEC2)
    c.drawString(40, y - 10, f"TOTAL: ${total:.2f}")
    c.setFillColor(black)

    # CAE
    y -= 40
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"CAE: {cae}")
    c.drawString(200, y, f"Vto. CAE: {cae_vto}")

    # QR
    try:
        qr_buf = generar_qr_afip(cuit, pto_vta, cbte_nro, cae, cae_vto)
        qr_img = ImageReader(qr_buf)
        c.drawImage(qr_img, width - 160, 40, width=120, height=120)
    except Exception as e:
        print("Error generando QR:", e)

    c.showPage()
    c.save()

    return filename
