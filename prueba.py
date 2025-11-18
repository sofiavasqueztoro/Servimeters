import requests
import time

TOKEN = "66ec83dd4fc6458efe534932a3eb46e54583b6e7"
BASE  = "http://localhost/dolibarr/api/index.php"

headers = {
    "DOLAPIKEY": TOKEN,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def crear_proyecto():
    ref = "TEST-" + time.strftime("%Y%m%d-%H%M%S")

    data = {
        "ref": ref,
        "title": "Proyecto de prueba desde script",
        "description": "Creado con prueba_post.py",
        "fk_statut": 1  # en muchas versiones = borrador/abierto
    }

    url = f"{BASE}/projects"
    r = requests.post(url, json=data, headers=headers, timeout=10)

    print("POST", url)
    print("Status:", r.status_code)
    print("Texto:", r.text)

if __name__ == "__main__":
    crear_proyecto()
