import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color, black

# -----------------------------
# PALETA DE COLORES
# -----------------------------
COLOR_PRIMARIO = Color(0.027, 0.133, 0.282)   # #072248
COLOR_SEC1 = Color(0.976, 0.592, 0.0)         # #F89700
COLOR_SEC2 = Color(0.113, 0.584, 0.760)       # #1D95C2
COLOR_SEC3 = Color(0.937, 0.078, 0.463)       # #EF1476
COLOR_SEC4 = Color(0.875, 0.863, 0.0)         # #DFDC00

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
    Genera un PDF de Factura C AFIP con diseño embellecido + logo.
    Devuelve la ruta local al archivo PDF creado.
    """

    # -------------------------------------
    # Carpeta donde se van a guardar los PDFs
    # -------------------------------------
    folder = "generated_pdfs"
    os.makedirs(folder, exist_ok=True)

    filename = f"{folder}/factura_C_{pto_vta:04d}_{cbte_nro:08d}.pdf"

    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    # -------------------------------------
    # Logo
    # -------------------------------------
    logo_path = "static/logo.png"
    if os.path.exists(logo_path):
        logo = ImageReader(logo_path)
        c.drawImage(logo, 40, height - 120, width=120, preserveAspectRatio=True, mask='auto')

    # -------------------------------------
    # Encabezado azul
    # -------------------------------------
    c.setFillColor(COLOR_PRIMARIO)
    c.rect(0, height - 40, width, 40, fill=True, stroke=False)

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(180, height - 30, "FACTURA C")

    # -------------------------------------
    # Datos del negocio
    # -------------------------------------
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, height - 150, razon_social)

    c.setFont("Helvetica", 10)
    c.drawString(40, height - 165, domicilio)
    c.drawString(40, height - 180, f"CUIT: {cuit}")

    # Punto de venta desde ENV
    c.drawString(40, height - 195, f"Punto de Venta: {pto_vta:04d}")
    c.drawString(220, height - 195, f"Comp. Nº: {cbte_nro:08d}")

    c.drawString(40, height - 210, f"Fecha: {fecha}")

    # -------------------------------------
    # Datos del cliente
    # -------------------------------------
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, height - 240, "Datos del Cliente")

    c.setFont("Helvetica", 10)
    c.drawString(40, height - 255, f"Nombre: {cliente_nombre}")

    if cliente_dni:
        c.drawString(40, height - 270, f"DNI: {cliente_dni}")
    else:
        c.drawString(40, height - 270, "DNI: Consumidor Final")

    # -------------------------------------
    # Tabla productos
    # -------------------------------------
    y = height - 310

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
        st = cant * precio

        c.drawString(40, y, desc[:40])
        c.drawString(300, y, str(cant))
        c.drawString(360, y, f"${precio:.2f}")
        c.drawString(440, y, f"${st:.2f}")
        y -= 18

    # -------------------------------------
    # Total
    # -------------------------------------
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(COLOR_SEC2)
    c.drawString(40, y - 10, f"TOTAL: ${total:.2f}")
    c.setFillColor(black)

    # -------------------------------------
    # CAE
    # -------------------------------------
    y -= 40
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"CAE: {cae}")
    c.drawString(200, y, f"Vto. CAE: {cae_vto}")

    # -------------------------------------
    # Final
    # -------------------------------------
    c.showPage()
    c.save()

    return filename
