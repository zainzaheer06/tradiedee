import requests
import json

API_URL = "https://demo.nevoxai.com/api/v1/calls/outbound"
API_KEY = "nvx_cffb28eaa6b13237e689af4b43e86860"

payload = {
    "agent_id": 123,
    "phone_number": "923354646825",
    "context": {
        "customer_name": "Ahmed",
        "order_id": "ORD-456"
    }
}

headers = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

try:
    response = requests.post(API_URL, headers=headers, json=payload)

    print("Status Code:", response.status_code)
    print("Response:")
    try:
        print(json.dumps(response.json(), indent=4))
    except ValueError:
        print(response.text or "(empty response body)")

except requests.exceptions.RequestException as e:
    print("Error occurred:", str(e))
