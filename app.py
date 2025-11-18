from flask import Flask, request, redirect
import requests

app = Flask(__name__)

# =========================
# CONFIGURACIÓN DOLIBARR
# =========================
DOLIBARR_BASE_URL = "http://localhost/dolibarr"  # Cambia si tu ruta es diferente
DOLIBARR_API_URL = f"{DOLIBARR_BASE_URL}/api/index.php"
DOLI_API_KEY = "A6IZFp4qcTeQ2mu6Kz42jT45Song9Q3E"  # <-- Pega aquí tu API KEY de Dolibarr

# =========================
# "Base de datos" en memoria
# =========================
messages = []       # historial de chat
opportunities = []  # oportunidades mostradas en el panel derecho


import time

def crear_lead_en_dolibarr(titulo, detalle):
    """
    Crea un Lead/Project en Dolibarr usando la API REST (/projects).
    """
    url = f"{DOLIBARR_API_URL}/projects"

    # Generamos una ref única tipo WHA-20241118-123456
    ref = "WHA-" + time.strftime("%Y%m%d-%H%M%S")

    data = {
        "ref": ref,
        "title": titulo,
        "description": detalle,
        "fk_statut": 1   # 1 = abierto / borrador
    }

    headers = {
        "DOLAPIKEY": DOLI_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(url, json=data, headers=headers, timeout=5)
        print("Dolibarr /projects →", resp.status_code, resp.text)
        if resp.status_code == 200:
            try:
                return resp.json().get("id"), ref
            except Exception:
                return None, ref
        else:
            return None, ref
    except Exception as e:
        print("Error al llamar /projects:", e)
        return None, ref

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
            en una oportunidad dentro del ERP (Dolibarr), a través de un middleware que mapea los datos
            y llama a la API REST.
          </p>
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
              <div class="small">Cliente: {o['customer']}</div>
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
    Cuando el "cliente" envía un mensaje en el WhatsApp,
    lo guardamos en el chat y creamos una oportunidad en Dolibarr.
    """
    text = request.form.get("text", "").strip()
    if text:
        # 1. Guardar mensaje en el chat simulado
        messages.append({"sender": "cliente", "text": text})

        # 2. Generar título de la oportunidad (motor de reglas simple)
        titulo = extraer_titulo_desde_mensaje(text)

        # 3. Crear lead/proyecto en Dolibarr vía API REST
        dolibarr_id, ref = crear_lead_en_dolibarr(titulo, text)

        # 4. Guardar también en la "base" local para mostrar en el panel derecho
        opportunity = {
            "title": titulo,
            "customer": "Cliente WhatsApp +57 318 302 1160",
            "detail": text,
            "id": dolibarr_id,
            "ref": ref
        }
        opportunities.append(opportunity)


    return redirect("/")


if __name__ == "__main__":
    # debug=True solo para desarrollo
    app.run(debug=True)
