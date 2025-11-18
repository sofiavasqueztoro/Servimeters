from flask import Flask, request, redirect
import requests

app = Flask(__name__)

# =========================
# CONFIGURACIÓN DOLIBARR
# =========================
DOLIBARR_BASE_URL = "http://localhost/dolibarr"  # Cambia si tu ruta es diferente
DOLIBARR_API_URL = f"{DOLIBARR_BASE_URL}/api/index.php"
DOLI_API_KEY = "66ec83dd4fc6458efe534932a3eb46e54583b6e7"  # <-- Pega aquí tu API KEY de Dolibarr

# =========================
# "Base de datos" en memoria
# =========================
messages = []       # historial de chat
opportunities = []  # oportunidades mostradas en el panel derecho


import time

def crear_lead_en_dolibarr(titulo, detalle, telefono):
    """
    Crea un Prospect + Lead/Project en Dolibarr:
    - Crea el thirdparty como prospecto
    - Crea el proyecto/oportunidad con monto y probabilidad estimados
    """
    # 1. Crear prospecto en Dolibarr
    thirdparty_id, nombre_cliente = crear_cliente_desde_whatsapp(telefono)

    # 2. Preparar proyecto/oportunidad
    url = f"{DOLIBARR_API_URL}/projects"
    ref = "WHA-" + time.strftime("%Y%m%d-%H%M%S")

    meta = extraer_metadata(detalle)

    data = {
        "ref": ref,
        "title": titulo,
        "description": detalle,
        "fk_statut": 1,             # abierto/borrador
        "public": 1,

        # Marcar como oportunidad
        "usage_opportunity": 1,
        "opp_status": 1,                               # abierta
        "opp_label": meta["tipo"],                    # RETIE / INSPECCION / etc
        "opp_amount": meta["monto_estimado"],         # <-- esto alimenta la tabla de leads
        "opp_percent": meta["probabilidad"],          # <-- para weighted amount

        # Localización básica
        "town": meta["ciudad"] or "",
        "date_start": int(time.time()),
    }

    # Vincular prospecto si se creó bien
    if thirdparty_id is not None:
        data["fk_soc"] = thirdparty_id

    headers = {
        "DOLAPIKEY": DOLI_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(url, json=data, headers=headers, timeout=5)
        print("Dolibarr /projects →", resp.status_code, resp.text)
        resp.raise_for_status()

        try:
            project_id = int(resp.text.strip())
        except ValueError:
            project_id = None

        return project_id, ref, thirdparty_id, nombre_cliente

    except Exception as e:
        print("Error al llamar /projects:", e)
        return None, ref, thirdparty_id, nombre_cliente


def extraer_titulo_desde_mensaje(texto):
    """
    Regla simple para generar el título de la oportunidad.
    Aquí simulas el motor de reglas del middleware.
    """
    texto = texto.strip()

    # Detectar algunos tipos típicos
    lower = texto.lower()
    if "retie" in lower:
        base = "Certificación RETIE"
    elif "inspección" in lower:
        base = "Inspección eléctrica"
    elif "calibración" in lower:
        base = "Servicio de calibración"
    else:
        base = "Nueva oportunidad desde WhatsApp"

    # Añadir un pequeño recorte del mensaje
    if len(texto) > 40:
        resumen = texto[:40] + "..."
    else:
        resumen = texto

    return f"{base} – {resumen}"

def extraer_metadata(texto):
    """
    A partir del mensaje de WhatsApp detectamos:
    - tipo de servicio (RETIE, inspección, calibración, otro)
    - urgencia (normal / alta)
    - ciudad
    - monto estimado (para estadísticas de leads)
    - probabilidad (para weighted amount)
    """
    t = texto.lower()

    # Tipo de servicio + monto base
    if "retie" in t:
        tipo = "RETIE"
        monto = 1_500_000
    elif "inspección" in t or "inspeccion" in t:
        tipo = "INSPECCION"
        monto = 900_000
    elif "calibración" in t or "calibracion" in t:
        tipo = "CALIBRACION"
        monto = 700_000
    else:
        tipo = "OTRO"
        monto = 500_000  # valor genérico

    # Urgencia
    urgencia = "normal"
    if "urgente" in t or "lo antes posible" in t or "ya mismo" in t:
        urgencia = "alta"

    # Ajuste simple por urgencia (demo)
    if urgencia == "alta":
        monto = int(monto * 1.2)

    # Probabilidad (para weighted amount)
    if tipo == "RETIE":
        prob = 80 if urgencia == "alta" else 70
    elif tipo in ("INSPECCION", "CALIBRACION"):
        prob = 70 if urgencia == "alta" else 60
    else:
        prob = 55 if urgencia == "alta" else 45

    # Ciudad (versión simple)
    ciudad = None
    for c in ["bogotá", "bogota", "medellín", "medellin", "cali"]:
        if c in t:
            ciudad = c.title()

    return {
        "tipo": tipo,
        "urgencia": urgencia,
        "ciudad": ciudad,
        "monto_estimado": monto,
        "probabilidad": prob,
    }


def crear_cliente_desde_whatsapp(telefono: str):
    """
    Crea un 'Thirdparty' marcado como PROSPECT en Dolibarr
    a partir del número de WhatsApp.
    """
    url = f"{DOLIBARR_API_URL}/thirdparties"

    nombre = f"Prospecto WhatsApp {telefono}"

    data = {
        "name": nombre,
        # client = 2  => Prospecto (no cliente todavía)
        "client": 2,
        "phone": telefono
    }

    headers = {
        "DOLAPIKEY": DOLI_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        resp = requests.post(url, json=data, headers=headers, timeout=5)
        print("Dolibarr /thirdparties →", resp.status_code, resp.text)
        resp.raise_for_status()

        try:
            thirdparty_id = int(resp.text.strip())
        except ValueError:
            thirdparty_id = None

        return thirdparty_id, nombre

    except Exception as e:
        print("Error al llamar /thirdparties:", e)
        return None, nombre




@app.route("/")
def chat():
    # HTML completo con chat + panel de oportunidades
    html = """
    <html>
    <head>
        <title>WhatsApp ➜ ERP (Dolibarr)</title>
        <style>
            body { font-family: Arial, sans-serif; background:#f0f2f5; margin:0; padding:0; }
            .topbar { background:#075E54; color:#fff; padding:10px 20px; font-size:18px; font-weight:bold; }
            .container { display:flex; height:calc(100vh - 40px); }
            .chat { flex:1; padding:20px; background:#ece5dd; display:flex; flex-direction:column; }
            .header { font-size:18px; font-weight:bold; margin-bottom:10px; }
            .messages { flex:1; overflow-y:auto; border-radius:10px; padding:10px; background:#fff; }
            .msg { margin:5px 0; padding:8px 12px; border-radius:15px; max-width:70%; font-size:14px; }
            .msg.client { background:#fff; align-self:flex-start; }
            .msg.agent { background:#dcf8c6; align-self:flex-end; }
            .sender { font-size:11px; color:#555; }
            .input-area { margin-top:10px; display:flex; }
            .input-area input { flex:1; padding:10px; border-radius:20px; border:1px solid #ccc; font-size:14px; }
            .input-area button { margin-left:10px; padding:10px 20px; border:none; border-radius:20px; background:#25d366; color:#fff; font-weight:bold; cursor:pointer; }
            .input-area button:hover { opacity:0.9; }
            .sidebar { width:420px; background:#ffffff; padding:20px; border-left:1px solid #ddd; overflow-y:auto; }
            .sidebar h2 { margin-top:0; }
            .small { font-size:12px; color:#666; }
            .opp { border-bottom:1px solid #eee; padding:8px 0; }
            .opp-title { font-weight:bold; }
            .tag { display:inline-block; font-size:11px; padding:2px 6px; border-radius:10px; background:#e0f7fa; margin-right:4px; }
            .id-pill { display:inline-block; font-size:11px; padding:2px 6px; border-radius:10px; background:#ffe0b2; margin-left:4px; }
        </style>
    </head>
    <body>
      <div class="topbar">Demo integración WhatsApp ➜ Middleware ➜ Dolibarr (ERP)</div>
      <div class="container">
        <div class="chat">
          <div class="header">WhatsApp Business – Chat con Cliente</div>
          <div class="messages">
    """

    # Renderizar los mensajes del chat
    for m in messages:
        css_class = "client" if m["sender"] == "cliente" else "agent"
        html += f'''
        <div class="msg {css_class}">
            <div class="sender">{m["sender"].title()}</div>
            {m["text"]}
        </div>
        '''

    html += """
          </div>
          <form method="POST" action="/send" class="input-area">
            <input type="text" name="text" placeholder="Escribe el mensaje del cliente..." autocomplete="off" required />
            <button type="submit">Enviar</button>
          </form>
        </div>

        <div class="sidebar">
          <h2>ERP / CRM – Oportunidades (Dolibarr)</h2>
          <p class="small">
            Cada mensaje que entra por el canal de WhatsApp Business se transforma automáticamente
            en una <b>oportunidad de prospecto</b> dentro del ERP (Dolibarr), a través de un middleware
            que mapea los datos y llama a la API REST.
          </p>
    """

    # Panel derecho: oportunidades
    if not opportunities:
        html += "<p class='small'>Todavía no hay oportunidades creadas.</p>"
    else:
        for i, o in enumerate(opportunities, start=1):
            _id = o.get("id")
            html += f"""
            <div class="opp">
              <div class="opp-title">
                Oportunidad #{i}: {o['title']}
                {f"<span class='id-pill'>ID Dolibarr: {_id}</span>" if _id else ""}
              </div>
              <div class="small">Prospecto: {o['customer']}</div>
              <div class="small">Detalle: {o['detail']}</div>
              <div class="small">
                <span class="tag">Canal: WhatsApp Business</span>
                <span class="tag">Estado: Prospecto</span>
              </div>
            </div>
            """

    html += """
        </div>
      </div>
    </body>
    </html>
    """

    return html


@app.route("/send", methods=["POST"])
def send():
    """
    Cuando el 'cliente' envía un mensaje en el WhatsApp,
    lo guardamos en el chat y creamos una oportunidad en Dolibarr.
    """
    text = request.form.get("text", "").strip()
    if text:
        # 1. Guardar mensaje en el chat simulado
        messages.append({"sender": "cliente", "text": text})

        # 2. Generar título de la oportunidad (motor de reglas simple)
        titulo = extraer_titulo_desde_mensaje(text)

        # Para el prototipo usamos un único número fijo
        telefono = "+57 318 302 1160"

        # 3. Crear prospecto + proyecto en Dolibarr vía API REST
        dolibarr_id, ref, thirdparty_id, nombre_cliente = crear_lead_en_dolibarr(
            titulo,
            text,
            telefono
        )

        # 4. Guardar también en la "base" local para mostrar en el panel derecho
        opportunity = {
            "title": titulo,
            "customer": nombre_cliente,      # se muestra como Prospecto
            "detail": text,
            "id": dolibarr_id,
            "ref": ref,
            "thirdparty_id": thirdparty_id,
            "phone": telefono,
        }
        opportunities.append(opportunity)

    return redirect("/")




if __name__ == "__main__":
    # debug=True solo para desarrollo
    app.run(debug=True)
