@router.get("/ventas")
async def listar_ventas(
    desde: date = Query(...),
    hasta: date = Query(...),
):
    return [
        {
            "receipt_id": "TEST-1",
            "receipt_type": "SALE",
            "fecha": "2025-12-16T00:00:00Z",
            "total": 1000,
            "pagos": [],
            "refund_status": "NONE",
            "refunded_amount": 0,
            "max_facturable": 1000,
            "items": [],
            "items_facturables": [],
            "refunded_items": [],
            "already_invoiced": False,
            "invoice": None,
        }
    ]
