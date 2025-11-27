# pdf_afip.py
import io
import json
import base64
from datetime import datetime

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


def _formatear_fecha_aaaammdd(fecha_aaaammdd: str) -> str:
    """
    Convierte 'YYYYMMDD' -> 'DD/MM/YYYY'
    """
    if not fecha_aaaammdd or len(fecha_aaaammdd) != 8:
        return fecha_aaaammdd or ""
    yyyy = fecha_aaaammdd[0:4]
    mm_ = fecha_aaaammdd[4:6]
    dd = fecha_aaaammdd[6:8]
    return f"{dd}/{mm_}/{yyyy}"


def generar_qr_afip(
    fecha_cbte_aaaammdd: str,
    cuit_emisor: str,
    pto_vta: int,
    tipo_cbte: int,
    cbte_nro: int,
    total: float,
    doc_tipo: int,
    doc_nro: int,
    cae: str,
):
    """
    Genera la URL de QR de AFIP según especificación oficial.
    """
    fecha_iso = None
    # fecha en formato YYYY-MM-DD
    if fecha_cbte_aaaammdd and len(fecha_cbte_aaaammdd) == 8:
        yyyy = fecha_cbte_aaaammdd[0:4]
        mm_ = fecha_cbte_aaaammdd[4:6]
        dd = fecha_cbte_aaaammdd[6:8]
        fecha_iso = f"{yyyy}-{mm_}-{dd}"
    else:
        # fallback: hoy
        fecha_iso = datetime.now().strftime("%Y-%m-%d")

    data = {
        "ver": 1,
        "fecha": fecha_iso,
        "cuit": int(cuit_emisor),
        "ptoVta": int(pto_vta),
        "tipoCmp": int(tipo_cbte),
        "nroCmp": int(cbte_nro),
        "importe": float(total),
        "moneda": "PES",
        "ctz": 1,
        "tipoDocRec": int(doc_tipo),
        "nroDocRec": int(doc_nro),
        "tipoCodAut": "E",
        "codAut": int(cae) if cae.isdigit() else cae,
    }

    json_str = json.dumps(data, separators=(",", ":"))
    json_b64 = base64.urlsafe_b64encode(json_str.encode("utf-8")).decode("utf-8")
    url_qr = f"https://www.afip.gob.ar/fe/qr/?p={json_b64}"
    return url_qr


def generar_pdf_factura_c(datos: dict) -> bytes:
    """
    Genera un PDF de FACTURA C con QR AFIP.
    'datos' debe incluir:
      - razon_social
      - domicilio
      - cuit_emisor
      - pto_vta
      - tipo_cbte
      - cbte_nro
      - fecha_cbte (AAAAMMDD)
      - cliente_nombre
      - cliente_doc_tipo
      - cliente_doc_nro
      - items: [{descripcion, cantidad, precio_unitario, importe}]
      - total
      - cae
      - vto_cae (AAAAMMDD)
    """

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Margen
    x_margin = 20 * mm
    y_margin = 20 * mm

    # ----------------------------------------
    # Encabezado emisor
    # ----------------------------------------
    razon_social = datos.get("razon_social", "")
    domicilio = datos.get("domicilio", "")
    cuit_emisor = datos.get("cuit_emisor", "")
    pto_vta = datos.get("pto_vta", 1)
    tipo_cbte = datos.get("tipo_cbte", 11)
    cbte_nro = datos.get("cbte_nro", 0)
    fecha_cbte = datos.get("fecha_cbte", datetime.now().strftime("%Y%m%d"))

    fecha_cbte_str = _formatear_fecha_aaaammdd(fecha_cbte)

    # Título grande
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x_margin, height - y_margin, razon_social)

    c.setFont("Helvetica", 10)
    c.drawString(x_margin, height - y_margin - 15, f"CUIT: {cuit_emisor}")
    c.drawString(x_margin, height - y_margin - 30, domicilio)
    c.drawString(x_margin, height - y_margin - 45, "Responsable Monotributo")

    # Tipo y número de comprobante
    numero_str = f"{tipo_cbte:02d}-{int(pto_vta):04d}-{int(cbte_nro):08d}"
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - x_margin, height - y_margin, "FACTURA C")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - x_margin, height - y_margin - 15, f"N° {numero_str}")
    c.drawRightString(width - x_margin, height - y_margin - 30, f"Fecha: {fecha_cbte_str}")

    # ----------------------------------------
    # Datos del cliente
    # ----------------------------------------
    cliente_nombre = datos.get("cliente_nombre", "Consumidor Final")
    doc_tipo = datos.get("cliente_doc_tipo", 99)
    doc_nro = datos.get("cliente_doc_nro", 0)

    y_cliente = height - y_margin - 70
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_margin, y_cliente, "Cliente:")
    c.setFont("Helvetica", 10)
    c.drawString(x_margin + 60, y_cliente, cliente_nombre)

    y_cliente -= 14
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_margin, y_cliente, "Documento:")
    c.setFont("Helvetica", 10)
    c.drawString(x_margin + 70, y_cliente, f"{doc_tipo}-{doc_nro}" if doc_nro else "Consumidor Final")

    # ----------------------------------------
    # Items
    # ----------------------------------------
    items = datos.get("items", [])
    y_items = y_cliente - 30

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_margin, y_items, "Descripción")
    c.drawRightString(width - x_margin - 80, y_items, "Cant.")
    c.drawRightString(width - x_margin - 20, y_items, "Importe")
    y_items -= 10
    c.line(x_margin, y_items, width - x_margin, y_items)
    y_items -= 10

    c.setFont("Helvetica", 9)
    for it in items:
        if y_items < 60 * mm:  # salto de página simple si se llena
            c.showPage()
            y_items = height - y_margin

        desc = it.get("descripcion", "")
        cant = it.get("cantidad", 0)
        imp = it.get("importe", 0.0)

        c.drawString(x_margin, y_items, desc[:70])
        c.drawRightString(width - x_margin - 80, y_items, f"{cant}")
        c.drawRightString(width - x_margin - 20, y_items, f"{imp:,.2f}")
        y_items -= 12

    # Total
    total = datos.get("total", 0.0)
    y_total = y_items - 10
    c.line(x_margin, y_total, width - x_margin, y_total)
    y_total -= 20

    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - x_margin - 20, y_total, f"Total: $ {total:,.2f}")

    # ----------------------------------------
    # CAE y Vencimiento
    # ----------------------------------------
    cae = datos.get("cae", "")
    vto_cae = datos.get("vto_cae", "")
    vto_cae_str = _formatear_fecha_aaaammdd(vto_cae)

    y_cae = 60 * mm
    c.setFont("Helvetica", 9)
    c.drawString(x_margin, y_cae, f"CAE: {cae}")
    c.drawString(x_margin, y_cae - 12, f"Vto. CAE: {vto_cae_str}")

    # ----------------------------------------
    # QR de AFIP
    # ----------------------------------------
    url_qr = generar_qr_afip(
        fecha_cbte_aaaammdd=fecha_cbte,
        cuit_emisor=cuit_emisor,
        pto_vta=pto_vta,
        tipo_cbte=tipo_cbte,
        cbte_nro=cbte_nro,
        total=total,
        doc_tipo=doc_tipo,
        doc_nro=doc_nro,
        cae=cae,
    )

    qr_img = qrcode.make(url_qr)
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_reader = ImageReader(qr_buffer)

    qr_size = 35 * mm
    c.drawImage(
        qr_reader,
        width - x_margin - qr_size,
        y_cae - 10,
        qr_size,
        qr_size,
        preserveAspectRatio=True,
        mask="auto",
    )

    c.setFont("Helvetica", 6)
    c.drawRightString(width - x_margin, y_cae - 15, "Código QR AFIP")

    # ----------------------------------------
    # Finalizar
    # ----------------------------------------
    c.showPage()
    c.save()

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
