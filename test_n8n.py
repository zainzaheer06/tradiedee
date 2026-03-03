import requests

url = "https://automation.nevoxai.com/api/v1/workflows"
headers = {
    "X-N8N-API-KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxYjVjYjU4ZC04YWIwLTQ2OWMtYWFkMS1mNTcyNDk4NmJjNzUiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcwODIyMzYxfQ.VOVL0mZvnqAtpeWNvztmuFKIhWFEb_iTpVDq4-RNLCU"
}

response = requests.get(url, headers=headers)
print(response.json())
