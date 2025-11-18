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
@app.route("/")
def chat():
    # HTML completo con chat tipo WhatsApp + panel de oportunidades
    html = """
    <html>
    <head>
        <title>WhatsApp ➜ ERP (Dolibarr)</title>
        <meta charset="utf-8" />
        <style>
            * { box-sizing: border-box; }

            body {
                margin: 0;
                padding: 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
                background: #0a1014;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
            }

            .app-shell {
                width: 1200px;
                height: 90vh;
                background: #111b21;
                border-radius: 18px;
                overflow: hidden;
                box-shadow: 0 18px 45px rgba(0,0,0,0.6);
                display: flex;
                flex-direction: column;
            }

            .topbar {
                background: linear-gradient(90deg,#075E54,#128C7E);
                color: #fff;
                padding: 10px 20px;
                font-size: 16px;
                font-weight: 600;
                display: flex;
                align-items: center;
            }

            .topbar span {
                opacity: 0.9;
            }

            .container {
                flex: 1;
                display: flex;
                background: #202c33;
            }

            /* LADO IZQUIERDO – WHATSAPP FAKE */
            .chat-wrapper {
                flex: 0.6;
                padding: 18px;
                display: flex;
                justify-content: center;
                align-items: center;
            }

            .phone {
                width: 100%;
                max-width: 480px;
                height: 100%;
                border-radius: 18px;
                background: #0b141a;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                border: 1px solid rgba(255,255,255,0.06);
            }

            .wa-header {
                background: #202c33;
                color: #e9edef;
                padding: 10px 14px;
                display: flex;
                align-items: center;
                gap: 10px;
            }

            .wa-avatar {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                background: #00a884;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #fff;
                font-weight: 600;
                font-size: 14px;
            }

            .wa-header-text {
                display: flex;
                flex-direction: column;
            }

            .wa-header-text .name {
                font-size: 14px;
                font-weight: 600;
            }

            .wa-header-text .status {
                font-size: 11px;
                color: #8696a0;
            }

            .chat-bg {
                flex: 1;
                background: #111b21 url("https://i.imgur.com/Oa7H0tC.png");
                background-size: 350px;
                display: flex;
                flex-direction: column;
                padding: 10px 12px;
                overflow-y: auto;
            }

            .msg {
                margin: 4px 0;
                padding: 6px 10px 8px;
                border-radius: 10px;
                max-width: 75%;
                font-size: 13px;
                line-height: 1.4;
                position: relative;
                color: #e9edef;
                word-wrap: break-word;
            }

            .msg.client {
                background: #202c33;
                align-self: flex-start;
                border-bottom-left-radius: 0;
            }

            .msg.agent {
                background: #005c4b;
                align-self: flex-end;
                border-bottom-right-radius: 0;
            }

            .sender {
                font-size: 10px;
                color: #8696a0;
                margin-bottom: 2px;
            }

            .input-area-wrap {
                padding: 8px 10px;
                background: #202c33;
                border-top: 1px solid #202c33;
            }

            .input-area {
                display: flex;
                gap: 8px;
            }

            .input-area input {
                flex: 1;
                padding: 10px 14px;
                border-radius: 20px;
                border: none;
                outline: none;
                font-size: 13px;
                background: #202c33;
                color: #e9edef;
            }

            .input-area input::placeholder {
                color: #8696a0;
            }

            .input-area button {
                padding: 0 20px;
                border: none;
                border-radius: 20px;
                background: #00a884;
                color: #fff;
                font-weight: 600;
                font-size: 13px;
                cursor: pointer;
            }

            .input-area button:hover {
                filter: brightness(1.05);
            }

            /* LADO DERECHO – ERP */
            .sidebar {
                flex: 0.4;
                padding: 18px 20px;
                background: #111b21;
                border-left: 1px solid #202c33;
                color: #e9edef;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            .sidebar h2 {
                margin: 0 0 4px;
                font-size: 18px;
            }

            .sidebar h3 {
                margin: 0 0 10px;
                font-size: 14px;
                font-weight: 500;
                color: #8696a0;
            }

            .small {
                font-size: 12px;
                color: #8696a0;
            }

            .opp-list {
                margin-top: 10px;
                overflow-y: auto;
            }

            .opp {
                border-radius: 10px;
                background: #202c33;
                padding: 10px 12px;
                margin-bottom: 8px;
            }

            .opp-title {
                font-weight: 600;
                font-size: 13px;
                margin-bottom: 4px;
            }

            .tag {
                display: inline-block;
                font-size: 11px;
                padding: 2px 6px;
                border-radius: 10px;
                background:#202c33;
                border: 1px solid #00a884;
                color: #e9edef;
                margin-right: 4px;
            }

            .id-pill {
                display:inline-block;
                font-size:11px;
                padding:2px 6px;
                border-radius:10px;
                background:#ffe0b2;
                color:#8a4f00;
                margin-left:6px;
            }
        </style>
    </head>
    <body>
      <div class="app-shell">
        <div class="topbar">
          <span>Demo integración WhatsApp ➜ Middleware ➜ Dolibarr (ERP)</span>
        </div>
        <div class="container">

          <!-- LADO WHATSAPP -->
          <div class="chat-wrapper">
            <div class="phone">
              <div class="wa-header">
                <div class="wa-avatar">C</div>
                <div class="wa-header-text">
                  <span class="name">Cliente WhatsApp</span>
                  <span class="status">en línea</span>
                </div>
              </div>
              <div class="chat-bg">
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
              <div class="input-area-wrap">
                <form method="POST" action="/send" class="input-area">
                  <input type="text" name="text" placeholder="Escribe el mensaje del cliente..." autocomplete="off" required />
                  <button type="submit">Enviar</button>
                </form>
              </div>
            </div>
          </div>

          <!-- LADO ERP -->
          <div class="sidebar">
            <h2>ERP / CRM – Oportunidades</h2>
            <h3>Dolibarr (Proyectos tipo lead)</h3>
            <p class="small">
              Cada mensaje que entra por el canal de WhatsApp Business se transforma automáticamente
              en una <b>oportunidad de prospecto</b> dentro del ERP, a través del middleware.
            </p>

            <div class="opp-list">
    """

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
                <div class="small" style="margin-top:6px;">
                  <span class="tag">Canal: WhatsApp Business</span>
                  <span class="tag">Estado: Prospecto</span>
                </div>
              </div>
            """

    html += """
            </div>
          </div>

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
