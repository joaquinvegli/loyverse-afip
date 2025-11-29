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
COLOR_PRIMARIO = Color(0.027, 0.133, 0.282)   # Azul oscuro
COLOR_SEC1 = Color(0.976, 0.592, 0.0)         # Naranja
COLOR_SEC2 = Color(0.113, 0.584, 0.760)       # Celeste
COLOR_SEC3 = Color(0.937, 0.078, 0.463)       # Rosa
COLOR_SEC4 = Color(0.875, 0.863, 0.0)         # Amarillo


def generar_qr_afip(cuit, pto_vta, cbte_nro, cae, cae_vto):
    """
    Genera el QR AFIP válido según especificación.
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
    - Encabezado con logo + FACTURA C
    - Datos del comercio
    - Datos del cliente
    - Detalle de ítems
    - Total
    - CAE + vencimiento
    - QR AFIP
    - Pie de página con datos de Top Fundas
    """

    # Carpeta donde se guardan los PDFs
    folder = "generated_pdfs"
    os.makedirs(folder, exist_ok=True)

    filename = f"{folder}/factura_C_{pto_vta:04d}_{cbte_nro:08d}.pdf"

    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    # ======================================================
    # ENCABEZADO
    # ======================================================
    # Barra azul superior
    c.setFillColor(COLOR_PRIMARIO)
    c.rect(0, height - 60, width, 60, fill=True, stroke=False)

    # Texto "FACTURA C" centrado aproximadamente
    c.setFillColor("white")
    c.setFont("Helvetica-Bold", 22)
    c.drawString(200, height - 40, "FACTURA C")

    # Caja con letra "C" a la izquierda, estilo AFIP
    c.setFillColor("white")
    c.setStrokeColor("white")
    c.rect(40, height - 55, 30, 30, fill=True, stroke=True)
    c.setFillColor(COLOR_PRIMARIO)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(40 + 15, height - 55 + 8, "C")

    # Código de comprobante a la derecha
    c.setFillColor("white")
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(width - 40, height - 35, "Cod. 11")

    # ======================================================
    # LOGO
    # ======================================================
    logo_path = "static/logo_fixed.png"
    if os.path.exists(logo_path):
        try:
            img = ImageReader(logo_path)
            # Logo más pequeño, alineado a la izquierda
            c.drawImage(img, 40, height - 140, width=90, preserveAspectRatio=True, mask='auto')
        except Exception as e:
            print("Error dibujando logo:", e)
    else:
        print("Logo no encontrado en:", logo_path)

    # ======================================================
    # DATOS DEL COMERCIO
    # (bajados un poco para que NO se superpongan con nada)
    # ======================================================
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 11)

    # Bajamos ~20 puntos respecto a la versión anterior
    base_y_comercio = height - 185

    c.drawString(40, base_y_comercio, razon_social)

    c.setFont("Helvetica", 10)
    c.drawString(40, base_y_comercio - 15, domicilio)
    c.drawString(40, base_y_comercio - 30, f"CUIT: {cuit}")

    # Estos textos son genéricos, podés ajustarlos si querés
    c.drawString(40, base_y_comercio - 45, f"Punto de Venta: {pto_vta:04d}")
    c.drawString(220, base_y_comercio - 45, f"Comprobante Nº: {cbte_nro:08d}")
    c.drawString(40, base_y_comercio - 60, f"Fecha de emisión: {fecha}")

    # ======================================================
    # DATOS DEL CLIENTE
    # ======================================================
    c.setFont("Helvetica-Bold", 11)
    y_cliente_titulo = base_y_comercio - 95
    c.drawString(40, y_cliente_titulo, "Datos del Cliente")

    c.setFont("Helvetica", 10)
    c.drawString(40, y_cliente_titulo - 15, f"Nombre: {cliente_nombre or 'Consumidor Final'}")

    if cliente_dni:
        c.drawString(40, y_cliente_titulo - 30, f"DNI: {cliente_dni}")
    else:
        c.drawString(40, y_cliente_titulo - 30, "DNI: Consumidor Final")

    # ======================================================
    # ITEMS
    # ======================================================
    y = y_cliente_titulo - 65

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

        # Si se acerca demasiado al pie, podrías implementar salto de página
        # pero por ahora asumimos cantidad moderada de ítems.

    # ======================================================
    # TOTAL
    # ======================================================
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(COLOR_SEC2)
    c.drawString(40, y - 10, f"TOTAL: ${total:.2f}")
    c.setFillColor(black)

    # ======================================================
    # CAE + VENCIMIENTO (estilo AFIP, cerca del QR)
    # ======================================================
    y_cae = 160  # Fijo, para dejar espacio al pie y al QR
    c.setFont("Helvetica", 9)
    c.drawString(40, y_cae, f"CAE: {cae}")
    c.drawString(200, y_cae, f"Vencimiento CAE: {cae_vto}")

    # ======================================================
    # QR AFIP
    # ======================================================
    try:
        qr_buf = generar_qr_afip(cuit, pto_vta, cbte_nro, cae, cae_vto)
        qr_img = ImageReader(qr_buf)
        # Abajo a la derecha, como AFIP
        c.drawImage(qr_img, width - 160, 40, width=120, height=120)
    except Exception as e:
        print("Error generando QR:", e)

    # ======================================================
    # PIE DE PÁGINA
    # ======================================================
    c.setFont("Helvetica", 8)
    c.setFillColor(Color(0.3, 0.3, 0.3))  # Gris suave

    footer_y1 = 50
    footer_y2 = 36
    footer_y3 = 22

    c.drawString(40, footer_y1, "Tienda online: www.topfundas.com.ar")
    c.drawString(40, footer_y2, "WhatsApp: +54 9 291 435 7809    Instagram: @topfundasbb")
    c.drawString(
        40,
        footer_y3,
        "Gracias por su compra. Este comprobante fue generado automáticamente por el sistema de facturación de Top Fundas."
    )

    # ======================================================
    # FINALIZAR
    # ======================================================
    c.showPage()
    c.save()

    return filename
