from flask import Flask, request, redirect
import requests
import time
import os
from datetime import date, timedelta
from requests_oauthlib import OAuth1

app = Flask(__name__)

# =========================
# CONFIGURACIÓN NETSUITE
# =========================
NETSUITE_BASE_URL = "https://5845631-sb1.suitetalk.api.netsuite.com"
NETSUITE_OPPORTUNITY_URL = f"{NETSUITE_BASE_URL}/services/rest/record/v1/opportunity"
NETSUITE_REALM = "5845631_SB1"

# Idealmente estos vienen de variables de entorno
NETSUITE_CONSUMER_KEY = os.getenv(
    "NETSUITE_CONSUMER_KEY",
    "4a61b925af4e317b76ba9441b67ef658193da355b17deb4bfe2a7f2cf9553f3f",
)
NETSUITE_CONSUMER_SECRET = os.getenv(
    "NETSUITE_CONSUMER_SECRET",
    "bf9c440ecb0b2c469cb1b6fd4f30f4f6c0ee2c24d04a543254e30fdedba5ce6b",
)
NETSUITE_ACCESS_TOKEN = os.getenv(
    "NETSUITE_ACCESS_TOKEN",
    "32ff928e651fdfb7e9507d603b2d1956c78766a976497af1cbac4d5b466b9014",
)
NETSUITE_TOKEN_SECRET = os.getenv(
    "NETSUITE_TOKEN_SECRET",
    "5fc663a15998663e0b5f742b99501cafb00c2d8dd0ca4c9e0cbb8cb01d1af5d5",
)

# =========================
# "Base de datos" en memoria
# =========================
messages = [
    {
        "sender": "agent",
        "text": (
            "👋 Bienvenido a Servimeters.\n\n"
            "Por favor escribe primero el *nombre de tu empresa* y luego *lo que necesitas*.\n\n"
            "Ejemplo: Soy **CORPORACIÓN UNIVERSITARIA DEL META** y necesito una "
            "inspección RETIE para la sede de Villavicencio."
        ),
    }
]  # historial de chat
opportunities = []  # oportunidades mostradas en el panel derecho


# =========================
# HELPERS DE NEGOCIO
# =========================

def extraer_titulo_desde_mensaje(texto, nombre_cliente=None):
    """
    Genera un título limpio para la oportunidad.
    Si llega nombre_cliente lo usa, si no, usa un título genérico.
    """
    meta = extraer_metadata(texto)
    tipo = meta["tipo"]  # RETIE, INSPECCION, etc.

    if nombre_cliente:
        return f"{tipo.title()} – {nombre_cliente}"
    else:
        # compatibilidad con llamadas antiguas
        return f"{tipo.title()} – Oportunidad desde WhatsApp"


def extraer_metadata(texto):
    """
    A partir del mensaje de WhatsApp detectamos:
    - tipo de servicio (RETIE, inspección, calibración, otro)
    - urgencia (normal / alta)
    - ciudad
    - monto estimado
    - probabilidad
    """
    t = texto.lower()

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
        monto = 500_000

    urgencia = "normal"
    if "urgente" in t or "lo antes posible" in t or "ya mismo" in t:
        urgencia = "alta"

    if urgencia == "alta":
        monto = int(monto * 1.2)

    if tipo == "RETIE":
        prob = 80 if urgencia == "alta" else 70
    elif tipo in ("INSPECCION", "CALIBRACION"):
        prob = 70 if urgencia == "alta" else 60
    else:
        prob = 55 if urgencia == "alta" else 45

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


# =========================
# MAPEO SIMPLE CLIENTE / SALES REP (para pruebas)
# =========================

TEST_CLIENTES = {
    # keyword_en_texto: (id, nombre)
    "uniciencia": ("204201", "66475 Corporación Universitaria de Ciencia y Desarrollo UNICIENCIA"),
    "meta": ("98163", "40299 CORPORACION UNIVERSITARIA DEL META"),
    "crepes": ("98170", "40306 CREPES Y WAFFLES"),
    "daflor": ("96118", "39439 DAFLOR"),
    "alarm": ("97856", "39993 ALARMAC LTDA"),
}

TEST_SALES_REP = {
    "adriana": ("104048", "ADRIANA CAROLINA BUSTOS BUSTOS"),
    "ana": ("128855", "ANA CATERINE GOMEZ CASTILLO"),
    "andrea": ("224", "ANDREA SERRANO CORONADO"),
}


def extraer_nombre_cliente_desde_texto(texto: str):
    """
    Intenta extraer el nombre de la empresa cuando el cliente escribe algo como:
    'Hola, soy CORPORACIÓN UNIVERSITARIA DEL META y necesito...'
    """
    t = texto.strip()
    lower = t.lower()

    if "soy " in lower:
        idx = lower.find("soy ")
        nombre = t[idx + 4 :]  # lo que viene después de 'soy '

        # Cortar donde empiezan otras frases típicas
        for sep in [" y ", " quiero", " necesito", " requiero", ",", "."]:
            pos = nombre.lower().find(sep)
            if pos != -1:
                nombre = nombre[:pos]

        return nombre.strip().upper()

    return None


def detectar_cliente_desde_mensaje(texto):
    """
    Si coincide con un cliente de pruebas → devuelve (id, nombre).
    Si no, intenta extraer el nombre del texto y devuelve (None, nombre_deducido).
    """
    t = texto.lower()
    for keyword, (cid, nombre) in TEST_CLIENTES.items():
        if keyword in t:
            return cid, nombre

    nombre_deducido = extraer_nombre_cliente_desde_texto(texto) or "PROSPECTO WHATSAPP"
    return None, nombre_deducido


def detectar_sales_rep_desde_mensaje(texto):
    t = texto.lower()
    for keyword, (rid, nombre) in TEST_SALES_REP.items():
        if keyword in t:
            return rid, nombre
    # fallback: primera vendedora
    rid, nombre = next(iter(TEST_SALES_REP.values()))
    return rid, nombre


# =========================
# INTEGRACIÓN NETSUITE
# =========================

def _netsuite_auth():
    return OAuth1(
        NETSUITE_CONSUMER_KEY,
        client_secret=NETSUITE_CONSUMER_SECRET,
        resource_owner_key=NETSUITE_ACCESS_TOKEN,
        resource_owner_secret=NETSUITE_TOKEN_SECRET,
        signature_method="HMAC-SHA256",
        realm=NETSUITE_REALM,
    )


def crear_cliente_en_netsuite(nombre_cliente: str):
    """
    Crea un Customer sencillo en NetSuite.
    """
    url = f"{NETSUITE_BASE_URL}/services/rest/record/v1/customer"

    body = {
        "companyName": nombre_cliente,
    }

    headers = {
        "Content-Type": "application/json",
        "Prefer": "transient",
    }

    try:
        resp = requests.post(url, json=body, headers=headers, auth=_netsuite_auth(), timeout=10)
        print("NetSuite /customer →", resp.status_code, resp.text)
        resp.raise_for_status()

        data = resp.json()
        customer_id = data.get("id") or data.get("internalId")
        return customer_id
    except Exception as e:
        print("Error al crear cliente en NetSuite:", e)
        return None


def crear_oportunidad_en_netsuite(titulo, detalle, telefono):
    """
    Crea una Opportunity en NetSuite via REST.
    Si el cliente no existe en la base de pruebas, lo crea primero como Customer.
    """
    meta = extraer_metadata(detalle)

    # 1. Detectar cliente
    entity_id, nombre_cliente = detectar_cliente_desde_mensaje(detalle)

    # 2. Si no tenemos ID de cliente, crearlo en NetSuite
    if entity_id is None:
        entity_id = crear_cliente_en_netsuite(nombre_cliente)
        if entity_id is None:
            # No se pudo crear el cliente -> abortamos creación de oportunidad
            print("No se pudo crear el cliente, no se crea la oportunidad.")
            return None, None, nombre_cliente

    # 3. Detectar sales rep
    sales_rep_id, _ = detectar_sales_rep_desde_mensaje(detalle)

    # Fecha de cierre prevista: hoy + 15 días (ejemplo)
    expected_close = (date.today() + timedelta(days=15)).isoformat()

    body = {
        "entity": {"id": entity_id},
        "title": titulo,
        "memo": detalle,
        "probability": meta["probabilidad"],
        "expectedCloseDate": expected_close,
        "projectedTotal": meta["monto_estimado"],
        "salesRep": {"id": sales_rep_id},
        # Campos custom del ejemplo (ponlos como necesites)
        "custbody_sm_clasificacion_negocio": 13,
        "custbodysm_origen_de_prospecto": 17,
        "custbody_sm_lin_negocio": 1,
        "custbody_sm_subl_negocio": 3,
    }

    headers = {
        "Content-Type": "application/json",
        "Prefer": "transient",
    }

    try:
        resp = requests.post(
            NETSUITE_OPPORTUNITY_URL,
            json=body,
            headers=headers,
            auth=_netsuite_auth(),
            timeout=10,
        )
        print("NetSuite /opportunity →", resp.status_code, resp.text)
        resp.raise_for_status()

        opportunity_id = None
        try:
            data = resp.json()
            # NetSuite suele devolver "id" o "internalId" según la versión/record
            opportunity_id = data.get("id") or data.get("internalId")
        except ValueError:
            opportunity_id = None

        return opportunity_id, entity_id, nombre_cliente

    except Exception as e:
        print("Error al llamar NetSuite /opportunity:", e)
        return None, entity_id, nombre_cliente


# =========================
# VISTA WEB (CHAT + PANEL)
# =========================

@app.route("/")
def chat():
    # HTML completo con chat tipo WhatsApp + panel de oportunidades
    html = """
    <html>
    <head>
        <title>WhatsApp ➜ ERP (NetSuite)</title>
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
          <span>Demo integración WhatsApp ➜ Middleware ➜ NetSuite (ERP)</span>
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
                  <input
                    type="text"
                    name="text"
                    placeholder="Ej: Soy CORPORACIÓN UNIVERSITARIA DEL META y necesito una inspección RETIE para la sede de Villavicencio"
                    autocomplete="off"
                    required
                  />
                  <button type="submit">Enviar</button>
                </form>
              </div>
            </div>
          </div>

          <!-- LADO ERP -->
          <div class="sidebar">
            <h2>ERP / CRM – Oportunidades</h2>
            <h3>NetSuite (Opportunities)</h3>
            <p class="small">
              Cada mensaje que entra por el canal de WhatsApp Business se transforma automáticamente
              en una <b>oportunidad</b> dentro de NetSuite, a través del middleware.
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
                  {f"<span class='id-pill'>ID NetSuite: {_id}</span>" if _id else ""}
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
    text = request.form.get("text", "").strip()
    if text:
        # 1. Guardar mensaje en el chat simulado
        messages.append({"sender": "cliente", "text": text})

        # Para el prototipo usamos un único número fijo
        telefono = "+57 318 302 1160"

        # 2. Detectar cliente para usar el nombre en el título
        _, nombre_cliente_detectado = detectar_cliente_desde_mensaje(text)

        # 3. Generar título de la oportunidad usando tipo + nombre cliente
        titulo = extraer_titulo_desde_mensaje(text, nombre_cliente_detectado)

        # 4. Crear oportunidad en NetSuite vía API REST
        netsuite_id, entity_id, nombre_cliente = crear_oportunidad_en_netsuite(
            titulo,
            text,
            telefono,
        )

        # 5. Guardar también en la "base" local para mostrar en el panel derecho
        opportunity = {
            "title": titulo,
            "customer": nombre_cliente,
            "detail": text,
            "id": netsuite_id,
            "ref": entity_id,
            "phone": telefono,
        }
        opportunities.append(opportunity)

    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)
