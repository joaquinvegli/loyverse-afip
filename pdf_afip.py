import os
import json
import qrcode
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

LOGO_PATH = "static/logo.png"


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
    Genera un PDF de Factura C AFIP con diseño + logo + QR oficial.
    Devuelve la ruta local al archivo PDF creado.
    """

    # -------------------------------------
    # Carpeta PDFs
    # -------------------------------------
    folder = "generated_pdfs"
    os.makedirs(folder, exist_ok=True)

    filename = f"{folder}/factura_C_{pto_vta:04d}_{cbte_nro:08d}.pdf"

    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    # -------------------------------------
    # Header azul
    # -------------------------------------
    c.setFillColor(COLOR_PRIMARIO)
    c.rect(0, height - 60, width, 60, fill=True, stroke=False)

    c.setFillColor(Color(1, 1, 1))  # blanco
    c.setFont("Helvetica-Bold", 20)
    c.drawString(230, height - 35, "FACTURA C")

    # -------------------------------------
    # Logo
    # -------------------------------------
    if os.path.exists(LOGO_PATH):
        try:
            logo = ImageReader(LOGO_PATH)
            c.drawImage(logo, 40, height - 140, width=120, preserveAspectRatio=True, mask='auto')
        except:
            pass  # si falla, no rompe el PDF

    # -------------------------------------
    # Datos del emisor
    # -------------------------------------
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, height - 160, razon_social)

    c.setFont("Helvetica", 10)
    c.drawString(40, height - 175, domicilio)
    c.drawString(40, height - 190, f"CUIT: {cuit}")
    c.drawString(40, height - 205, f"Punto de Venta: {pto_vta:04d}")
    c.drawString(180, height - 205, f"Comp. Nº: {cbte_nro:08d}")
    c.drawString(40, height - 220, f"Fecha: {fecha}")

    # -------------------------------------
    # Datos del cliente
    # -------------------------------------
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, height - 250, "Datos del Cliente")

    c.setFont("Helvetica", 10)
    c.drawString(40, height - 265, f"Nombre: {cliente_nombre}")

    if cliente_dni:
        c.drawString(40, height - 280, f"DNI: {cliente_dni}")
    else:
        c.drawString(40, height - 280, "DNI: Consumidor Final")

    # -------------------------------------
    # Tabla de ítems
    # -------------------------------------
    y = height - 315

    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Descripción")
    c.drawString(300, y, "Cant.")
    c.drawString(360, y, "Precio")
    c.drawString(440, y, "Subtotal")

    y -= 10
    c.setStrokeColor(COLOR_SEC1)
    c.line(40, y, width - 40, y)
    y -= 22

    c.setFont("Helvetica", 10)

    for it in items:
        desc = it["descripcion"][:40]
        cant = it["cantidad"]
        precio = it["precio"]
        st = cant * precio

        c.drawString(40, y, desc)
        c.drawString(300, y, str(cant))
        c.drawString(360, y, f"${precio:.2f}")
        c.drawString(440, y, f"${st:.2f}")
        y -= 18

    # -------------------------------------
    # TOTAL
    # -------------------------------------
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(COLOR_SEC2)
    c.drawString(40, y - 10, f"TOTAL: ${total:.2f}")
    c.setFillColor(black)

    # -------------------------------------
    # CAE + vencimiento
    # -------------------------------------
    y -= 50
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"CAE: {cae}")
    c.drawString(200, y, f"Vto. CAE: {cae_vto}")

    # -------------------------------------
    # QR OFICIAL AFIP
    # -------------------------------------
    qr_data = {
        "ver": 1,
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "cuit": int(cuit),
        "ptoVta": pto_vta,
        "tipoCmp": 11,
        "nroCmp": cbte_nro,
        "importe": float(total),
        "moneda": "PES",
        "ctz": 1,
        "tipoDocRec": 96,
        "nroDocRec": int(cliente_dni) if cliente_dni else 0,
        "tipoCodAut": "E",
        "codAut": int(cae)
    }

    json_qr = json.dumps(qr_data).encode("utf-8")
    url_afip = "https://www.afip.gob.ar/fe/qr/?p=" + json_qr.decode("latin1")

    qr_img = qrcode.make(url_afip)

    qr_path = f"{folder}/qr_{pto_vta}_{cbte_nro}.png"
    qr_img.save(qr_path)

    # Insertar QR abajo a la derecha (formato oficial)
    if os.path.exists(qr_path):
        qr = ImageReader(qr_path)
        c.drawImage(qr, width - 160, 40, width=120, height=120)

    c.setFont("Helvetica", 8)
    c.drawString(width - 160, 30, "Consultar validez en afip.gob.ar/fe")

    # -------------------------------------
    # Finalizar
    # -------------------------------------
    c.showPage()
    c.save()

    return filename
