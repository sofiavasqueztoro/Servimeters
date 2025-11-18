from flask import Flask, request, redirect

app = Flask(__name__)

# "Base de datos" simplificada en memoria
messages = []          # Mensajes del chat
opportunities = []     # Oportunidades creadas

@app.route("/")
def chat():
    # HTML simple que simula WhatsApp Business
    html = """
    <html>
    <head>
        <title>WhatsApp Business – Demo</title>
        <style>
            body { font-family: Arial, sans-serif; background:#f5f5f5; margin:0; padding:0; }
            .container { display:flex; height:100vh; }
            .chat { flex:1; padding:20px; background:#ece5dd; display:flex; flex-direction:column; }
            .header { font-size:20px; font-weight:bold; margin-bottom:10px; }
            .messages { flex:1; overflow-y:auto; border-radius:10px; padding:10px; background:#fff; }
            .msg { margin:5px 0; padding:8px 12px; border-radius:15px; max-width:70%; }
            .msg.client { background:#fff; align-self:flex-start; }
            .msg.agent { background:#dcf8c6; align-self:flex-end; }
            .input-area { margin-top:10px; display:flex; }
            .input-area input { flex:1; padding:10px; border-radius:20px; border:1px solid #ccc; }
            .input-area button { margin-left:10px; padding:10px 20px; border:none; border-radius:20px; background:#25d366; color:#fff; font-weight:bold; cursor:pointer; }
            .sidebar { width:380px; background:#ffffff; padding:20px; border-left:1px solid #ddd; }
            .sidebar h2 { margin-top:0; }
            .opp { border-bottom:1px solid #eee; padding:8px 0; }
            .opp-title { font-weight:bold; }
            .tag { display:inline-block; font-size:11px; padding:2px 6px; border-radius:10px; background:#e0f7fa; margin-right:4px; }
            .small { font-size:12px; color:#666; }
        </style>
    </head>
    <body>
      <div class="container">
        <div class="chat">
          <div class="header">WhatsApp Business – Chat con Cliente</div>
          <div class="messages">
    """
    # Renderizar mensajes ya enviados
    for m in messages:
        css_class = "client" if m["sender"] == "cliente" else "agent"
        html += f'<div class="msg {css_class}"><span class="small">{m["sender"].title()}:</span><br>{m["text"]}</div>'

    html += """
          </div>
          <form method="POST" action="/send" class="input-area">
            <input type="text" name="text" placeholder="Escribe el mensaje del cliente..." autocomplete="off" required />
            <button type="submit">Enviar</button>
          </form>
        </div>

        <div class="sidebar">
          <h2>ERP / CRM – Oportunidades</h2>
          <p class="small">
            Cada mensaje enviado desde el chat se transforma automáticamente en una oportunidad de negocio en este módulo del ERP.
          </p>
    """

    # Renderizar oportunidades
    if not opportunities:
        html += "<p class='small'>Todavía no hay oportunidades creadas.</p>"
    else:
        for i, o in enumerate(opportunities, start=1):
            html += f"""
            <div class="opp">
              <div class="opp-title">Oportunidad #{i}: {o['title']}</div>
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
    text = request.form.get("text", "").strip()
    if text:
        # 1. Guardamos el mensaje en el "WhatsApp"
        messages.append({"sender": "cliente", "text": text})

        # 2. Simulamos el MIDDLEWARE creando una oportunidad automáticamente
        opportunity = {
            "title": extraer_titulo_desde_mensaje(text),
            "customer": "Cliente WhatsApp +57 318 302 1160",
            "detail": text
        }
        opportunities.append(opportunity)

    return redirect("/")


def extraer_titulo_desde_mensaje(texto):
    """
    Regla súper sencilla para generar un título de oportunidad desde el mensaje.
    En una integración real, esto lo haría el motor de reglas/mapeo.
    """
    texto = texto.strip()
    if len(texto) > 40:
        return texto[:40] + "..."
    if not texto:
        return "Nueva oportunidad desde WhatsApp"
    return texto


if __name__ == "__main__":
    app.run(debug=True)
