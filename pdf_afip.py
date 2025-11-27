# pdf_afip.py
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import Image
from datetime import datetime
import qrcode

# ============================================================
# GENERAR PDF PROFESIONAL DE FACTURA C
# ============================================================

def generar_pdf_factura(
    cbte_nro: int,
    cae: str,
    vto_cae: str,
    fecha_cbte: str,
    cliente_nombre: str,
    cliente_dni: str,
    cliente_email: str,
    items: list,
    total: float,
):
    """
    Genera un PDF profesional usando ReportLab.
    Devuelve path del PDF generado.
    """

    # ---------- Paths ----------
    output_path = f"/tmp/FacturaC_{cbte_nro}.pdf"
    logo_path = "./static/logo.png"

    punto_venta = os.environ.get("AFIP_PTO_VTA", "1")
    pto_vta_fmt = str(punto_venta).zfill(4)
    cbte_fmt = str(cbte_nro).zfill(8)

    # ---------- Fecha DD/MM/AAAA ----------
    try:
        fecha_formateada = datetime.strptime(fecha_cbte, "%Y%m%d").strftime("%d/%m/%Y")
    except:
        fecha_formateada = fecha_cbte

    # ---------- Crear PDF ----------
    c = canvas.Canvas(output_path, pagesize=A4)
    w, h = A4

    # Paleta recomendada
    azul = colors.HexColor("#072248")
    naranja = colors.HexColor("#F89700")
    celeste = colors.HexColor("#1D95C2")
    rosa = colors.HexColor("#EF1476")
    amarillo = colors.HexColor("#DFDC00")

    # ============================================================
    # LOGO
    # ============================================================
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 15*mm, h - 40*mm, width=45*mm, height=35*mm, preserveAspectRatio=True)

    # ============================================================
    # TÍTULO
    # ============================================================
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(azul)
    c.drawString(70*mm, h - 25*mm, "FACTURA C")

    c.setFont("Helvetica-Bold", 12)
    c.drawString(70*mm, h - 32*mm, f"Punto de Venta: {pto_vta_fmt}  |  Comp. Nº {pto_vta_fmt}-{cbte_fmt}")

    # ============================================================
    # DATOS DEL EMISOR (VOS)
    # ============================================================
    c.setFillColor(colors.black)
    y = h - 55*mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(15*mm, y, "Emisor:")
    y -= 5*mm

    c.setFont("Helvetica", 10)
    c.drawString(15*mm, y, "JOAQUIN VEGLI")
    y -= 5*mm
    c.drawString(15*mm, y, "CUIT: 20-39157186-5")
    y -= 5*mm
    c.drawString(15*mm, y, "Responsable Monotributo")
    y -= 5*mm
    c.drawString(15*mm, y, "Alsina 155 Local 15, Bahía Blanca, Buenos Aires, CP 8000")

    # ============================================================
    # DATOS DEL CLIENTE
    # ============================================================
    y -= 15*mm
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(azul)
    c.drawString(15*mm, y, "Datos del Cliente")
    y -= 4*mm

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)

    c.drawString(15*mm, y, f"Nombre: {cliente_nombre}")
    y -= 5*mm
    c.drawString(15*mm, y, f"DNI: {cliente_dni or 'Consumidor Final'}")
    y -= 5*mm
    if cliente_email:
        c.drawString(15*mm, y, f"Email: {cliente_email}")
        y -= 5*mm

    # ============================================================
    # ITEMS
    # ============================================================
    y -= 10*mm
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(azul)
    c.drawString(15*mm, y, "Detalle de Productos")
    y -= 6*mm

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)

    for item in items:
        texto = f"{item['nombre']}  x{item['cantidad']}  -  ${item['precio_unitario']}"
        c.drawString(15*mm, y, texto)
        y -= 5*mm

        if y < 40*mm:  # Nueva página si hace falta
            c.showPage()
            y = h - 30*mm

    # Total
    y -= 8*mm
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(naranja)
    c.drawString(15*mm, y, f"TOTAL: ${total}")
    c.setFillColor(colors.black)

    # ============================================================
    # CAE y VENCIMIENTO
    # ============================================================
    y -= 15*mm
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(azul)
    c.drawString(15*mm, y, "Datos AFIP")
    y -= 6*mm

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(15*mm, y, f"CAE: {cae}")
    y -= 5*mm
    c.drawString(15*mm, y, f"Vto CAE: {vto_cae}")
    y -= 10*mm

    # ============================================================
    # QR OBLIGATORIO
    # ============================================================
    qr_data = (
        f"https://www.afip.gob.ar/fe/qr/?p="
        f"{{"
        f"\"ver\":1,"
        f"\"fecha\":\"{fecha_formateada}\","
        f"\"cuit\":20391571865,"
        f"\"ptoVta\":{int(punto_venta)},"
        f"\"tipoCmp\":11,"
        f"\"nroCmp\":{cbte_nro},"
        f"\"importe\":{total},"
        f"\"moneda\":\"PES\","
        f"\"ctz\":1,"
        f"\"tipoDocRec\":96,"
        f"\"nroDocRec\":{cliente_dni or 0},"
        f"\"codAut\":{cae}"
        f"}}"
    )

    qr_img = qrcode.make(qr_data)
    qr_path = f"/tmp/qr_{cbte_nro}.png"
    qr_img.save(qr_path)

    c.drawImage(qr_path, 150*mm, 15*mm, width=40*mm, height=40*mm)

    # ============================================================
    # FINALIZAR PDF
    # ============================================================
    c.save()

    return output_path
