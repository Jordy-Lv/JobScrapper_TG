#!/usr/bin/env python3
"""Pre-run script: envía la imagen de encabezado al canal de Telegram.
Se ejecuta SIEMPRE antes de cada corrida del cron.
En las corridas no_agent, su stdout se entrega tal cual.
"""
import subprocess, sys

CHANNEL = "-1004429829042"
IMAGE = "/home/ByLOGAN/.hermes/cron/media/encabezado_vacantes.jpg"

def send(text):
    try:
        r = subprocess.run(
            ["hermes", "send", "-t", f"telegram:{CHANNEL}", text],
            capture_output=True, text=True, timeout=60,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)

# Enviar la imagen como encabezado
code, msg = send(f"MEDIA:{IMAGE}")
if code == 0:
    print(f"[encabezado] imagen enviada OK a {CHANNEL}")
    sys.exit(0)
else:
    # Reintento
    code, msg = send(f"MEDIA:{IMAGE}")
    if code == 0:
        print(f"[encabezado] imagen enviada OK a {CHANNEL} (reintento)")
        sys.exit(0)
    print(f"[encabezado] ERROR al enviar imagen: {msg}")
    sys.exit(0)  # no bloquear el cron por un error de imagen
