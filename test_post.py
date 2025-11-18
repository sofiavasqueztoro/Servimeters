import requests

API_URL = "http://localhost/dolibarr/api/index.php/opportunities"
API_KEY = "66ec83dd4fc6458efe534932a3eb46e54583b6e7"

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
