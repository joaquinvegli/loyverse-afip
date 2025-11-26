@app.get("/debug/server_time")
def debug_server_time():
    from datetime import datetime, timezone, timedelta

    now_local = datetime.now()  # hora local del contenedor
    now_utc = datetime.utcnow()  # hora UTC real
    now_utc_afip = datetime.utcnow() - timedelta(hours=3)  # lo que sería hora AFIP

    return {
        "server_local": now_local.strftime("%Y-%m-%d %H:%M:%S"),
        "server_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "afip_utc_minus3": now_utc_afip.strftime("%Y-%m-%d %H:%M:%S"),
        "unix_epoch_server": now_local.timestamp(),
        "unix_epoch_utc": now_utc.timestamp(),
        "diff_seconds": now_local.timestamp() - now_utc.timestamp(),
    }
