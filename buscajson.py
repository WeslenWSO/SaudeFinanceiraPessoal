import requests
import ssl

def cotacao(request):
    try:
        response = requests.get('https://api.exchangerate-api.com/v4/latest/USD', timeout=10)
        return response.json()
    except:
        return {}