import requests

API_URL = "http://localhost/dolibarr/api/index.php/opportunities"
API_KEY = "A6IZFp4qcTeQ2mu6Kz42jT45Song9Q3E"

def crear_oportunidad_en_dolibarr(titulo, mensaje):
    data = {
        "label": titulo,
        "description": mensaje,
        "opportunity_status": 1  # Prospecto
    }
    headers = {
        "DOLAPIKEY": API_KEY,
        "Content-Type": "application/json"
    }
    resp = requests.post(API_URL, json=data, headers=headers)
    print("Respuesta Dolibarr:", resp.status_code, resp.text)
