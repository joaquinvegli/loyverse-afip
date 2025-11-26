import os
import base64

var = os.getenv("AFIP_CERT_CRT")

print("==== ANALISIS AFIP_CERT_CRT ====\n")

if var is None:
    print("❌ La variable NO está definida en el entorno.")
    exit()

print(f"Longitud total: {len(var)} caracteres\n")

# Mostrar primeros y últimos caracteres para ver si hay basura
print("Primeros 80 chars:")
print(var[:80])
print("\nÚltimos 80 chars:")
print(var[-80:])
print("\n")

# Verificar si empieza y termina bien
print("¿Comienza con BEGIN CERTIFICATE?")
print(var.startswith("-----BEGIN CERTIFICATE-----"))

print("\n¿Termina con END CERTIFICATE?")
print(var.endswith("-----END CERTIFICATE-----"))

# Buscar caracteres invisibles
print("\nCaracteres sospechosos encontrados:")
for i, c in enumerate(var):
    if ord(c) < 32 and c not in ["\n", "\r", "\t"]:
        print(f" - Posición {i}: caracter ASCII {ord(c)}")

# Encode para ver si se rompe
try:
    base64.b64encode(var.encode("utf-8"))
    print("\n✔ Base64 encode OK. No hay bytes ilegales visibles.")
except Exception as e:
    print("\n❌ ERROR al convertir a base64:", e)

print("\n==== FIN DEL ANALISIS ====")
