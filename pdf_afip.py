import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color, black
from io import BytesIO
import requests
import qrcode

# -----------------------------
# PALETA DE COLORES
# -----------------------------
COLOR_PRIMARIO = Color(0.027, 0.133, 0.282)   # #072248
COLOR_SEC1 = Color(0.976, 0.592, 0.0)         # #F89700
COLOR_SEC2 = Color(0.113, 0.584, 0.760)       # #1D95C2
COLOR_SEC3 = Color(0.937, 0.078, 0.463)       # #EF1476
COLOR_SEC4 = Color(0.875, 0.863, 0.0)         # #DFDC00

# URL RAW del logo
LOGO_URL = "https://raw.githubusercontent.com/joaquinvegli/loyverse-afip/main/static/logo.png"


def cargar_logo_en_memoria():
    """
    Descarga el logo desde GitHub y lo deja en un BytesIO para evitar
    problemas de filesystem en Render y problemas de decodificación PNG.
    """
    try:
        resp = requests.get(LOGO_URL, timeout=10)
        if resp.status_code == 200:
            bio = BytesIO(resp.content)
            bio.seek(0)
            return ImageReader(bio)
        else:
            print("Error descargando logo:", resp.status_code)
    except Exception as e:
        print("Excepción descargando logo:", e)

    return None


def generar_qr_afip(cuit, pto_vta, cbte_nro, cae, cae_vto):
    """
    Genera un QR AFIP válido.
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
    buffer = BytesIO()
    qr_img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


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
    Genera el PDF de factura C con logo + QR.
    """

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

    c.setFillColor("white")
    c.setFont("Helvetica-Bold", 22)
    c.drawString(200, height - 40, "FACTURA C")

    # -------------------------------------
    # LOGO DESDE MEMORIA (INFALIBLE)
    # -------------------------------------
    logo_img = cargar_logo_en_memoria()
    if logo_img:
        try:
            c.drawImage(logo_img, 40, height - 140, width=100, preserveAspectRatio=True, mask='auto')
        except Exception as e:
            print("Error dibujando logo:", e)
    else:
        print("Logo no disponible, no se dibuja.")

    # -------------------------------------
    # Datos del comercio
    # -------------------------------------
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, height - 165, razon_social)

    c.setFont("Helvetica", 10)
    c.drawString(40, height - 180, domicilio)
    c.drawString(40, height - 195, f"CUIT: {cuit}")

    c.drawString(40, height - 210, f"Punto de Venta: {pto_vta:04d}")
    c.drawString(220, height - 210, f"Comprobante Nº: {cbte_nro:08d}")

    c.drawString(40, height - 225, f"Fecha: {fecha}")

    # -------------------------------------
    # Datos del cliente
    # -------------------------------------
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, height - 260, "Datos del Cliente")

    c.setFont("Helvetica", 10)
    c.drawString(40, height - 275, f"Nombre: {cliente_nombre}")

    if cliente_dni:
        c.drawString(40, height - 290, f"DNI: {cliente_dni}")
    else:
        c.drawString(40, height - 290, "DNI: Consumidor Final")

    # -------------------------------------
    # Items
    # -------------------------------------
    y = height - 330

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
    # QR AFIP
    # -------------------------------------
    try:
        qr_buf = generar_qr_afip(cuit, pto_vta, cbte_nro, cae, cae_vto)
        qr_img = ImageReader(qr_buf)
        c.drawImage(qr_img, width - 160, 40, width=120, height=120)
    except Exception as e:
        print("Error generando QR:", e)

    # -------------------------------------
    # Final
    # -------------------------------------
    c.showPage()
    c.save()

    return filename
