from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import qrcode
import base64
import json
from datetime import datetime
import os


# ===========================================
# GENERAR QR OFICIAL AFIP (RG 4892)
# ===========================================
def generar_qr_afip(fecha, cuit, pto_vta, tipo_cbte, nro_cbte, total, cae,
                    tipo_doc_rec=99, nro_doc_rec=0, iva_cond_rec=4):
    """
    Genera QR OFICIAL AFIP (versión 2025-2026)
    con campos obligatorios desde 01/02/2026.
    """

    # Fecha en formato YYYY-MM-DD
    fecha_afip = datetime.strptime(fecha, "%d/%m/%Y").strftime("%Y-%m-%d")

    payload = {
        "ver": 1,
        "fecha": fecha_afip,
        "cuit": int(cuit),
        "ptoVta": int(pto_vta),
        "tipoCmp": int(tipo_cbte),
        "nroCmp": int(nro_cbte),
        "importe": float(total),
        "moneda": "PES",
        "ctz": 1,

        # -----------------------------
        # Campos del receptor (obligatorios)
        # -----------------------------
        "tipoDocRec": int(tipo_doc_rec),
        "nroDocRec": int(nro_doc_rec),

        # 🔥 Campo obligatorio desde 01/02/2026
        "ivaCond": int(iva_cond_rec),

        # -----------------------------
        # Datos de autorización AFIP
        # -----------------------------
        "tipoCodAut": "E",
        "codAut": int(cae)
    }

    payload_str = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_str.encode("utf-8")).decode("utf-8")

    url_qr = f"https://www.afip.gob.ar/fe/qr/?p={payload_b64}"

    qr = qrcode.make(url_qr)
    return qr


# ===========================================
# GENERAR PDF FACTURA C
# ===========================================
def generar_pdf_factura_c(
    razon_social,
    domicilio,
    cuit,
    pto_vta,
    cbte_nro,
    fecha,
    cae,
    cae_vto,
    cliente_nombre,
    cliente_dni,
    items,
    total
):

    pdf_path = f"factura_{cbte_nro}.pdf"
    c = canvas.Canvas(pdf_path, pagesize=A4)

    # ===========================
    # LOGO
    # ===========================
    logo_path = "static/logo.png"
    if os.path.exists(logo_path):
        try:
            c.drawImage(ImageReader(logo_path), 15*mm, 265*mm, width=40*mm, preserveAspectRatio=True)
        except:
            pass

    # ===========================
    # ENCABEZADO
    # ===========================
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60*mm, 280*mm, "FACTURA C")

    c.setFont("Helvetica", 10)
    c.drawString(15*mm, 255*mm, razon_social)
    c.drawString(15*mm, 250*mm, domicilio)
    c.drawString(15*mm, 245*mm, f"CUIT: {cuit}")
    c.drawString(15*mm, 240*mm, f"Punto de venta: {pto_vta:04d}  -  Comp. Nº: {cbte_nro}")
    c.drawString(15*mm, 235*mm, f"Fecha: {fecha}")

    # ===========================
    # CLIENTE
    # ===========================
    c.setFont("Helvetica-Bold", 12)
    c.drawString(15*mm, 225*mm, "Cliente:")
    c.setFont("Helvetica", 10)

    c.drawString(15*mm, 220*mm, f"Nombre: {cliente_nombre or 'Consumidor Final'}")
    c.drawString(15*mm, 215*mm, f"DNI: {cliente_dni or '-'}")

    # ===========================
    # ITEMS
    # ===========================
    y = 200 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(15*mm, y, "Descripción")
    c.drawString(130*mm, y, "Total")
    y -= 5 * mm
    c.setFont("Helvetica", 10)

    for it in items:
        c.drawString(15*mm, y, f"{it['descripcion']} (x{it['cantidad']})")
        c.drawRightString(195*mm, y, f"${it['precio']*it['cantidad']:.2f}")
        y -= 5*mm

    # ===========================
    # TOTAL
    # ===========================
    y -= 10*mm
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(195*mm, y, f"TOTAL: ${total:.2f}")

    # ===========================
    # CAE
    # ===========================
    y -= 15*mm
    c.setFont("Helvetica", 10)
    c.drawString(15*mm, y, f"CAE: {cae}")
    y -= 5*mm
    c.drawString(15*mm, y, f"Vencimiento CAE: {cae_vto}")

    # ===========================
    # QR OFICIAL AFIP
    # ===========================
    qr = generar_qr_afip(
        fecha=fecha,
        cuit=cuit,
        pto_vta=pto_vta,
        tipo_cbte=11,
        nro_cbte=cbte_nro,
        total=total,
        cae=cae,
        tipo_doc_rec=99,
        nro_doc_rec=0,
        iva_cond_rec=4    # Consumidor Final
    )

    qr_path = f"qr_{cbte_nro}.png"
    qr.save(qr_path)

    # Insertar QR abajo a la derecha
    c.drawImage(qr_path, 150*mm, 10*mm, width=40*mm, height=40*mm)

    c.save()

    return pdf_path
