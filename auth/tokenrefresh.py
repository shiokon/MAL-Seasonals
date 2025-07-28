import requests
import json
import os
from auth import config

client_id = config.CLIENT_ID
client_secret = config.CLIENT_SECRET

def exchange_code_for_tokens(authorization_code, code_verifier):
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": authorization_code,
        "code_verifier": code_verifier
    }

    response = requests.post("https://myanimelist.net/v1/oauth2/token", data=data)
    if response.status_code == 200:
        tokens = response.json()
        with open("tokens.json", "w") as f:
            json.dump(tokens, f)
        print("Tokens saved to tokens.json")
        return tokens
    else:
        print("Error:", response.status_code, response.text)
        return None

def refresh_token():
    try:
        with open("tokens.json", "r") as f:
            tokens = json.load(f)
    except FileNotFoundError:
        print("No tokens found. Please run initial authorization first.")
        return None

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": tokens.get("refresh_token")
    }

    response = requests.post("https://myanimelist.net/v1/oauth2/token", data=data)
    if response.status_code == 200:
        new_tokens = response.json()
        with open("tokens.json", "w") as f:
            json.dump(new_tokens, f)
        print("Tokens refreshed and saved.")
        return new_tokens
    else:
        print("Failed to refresh token:", response.status_code, response.text)
        return None

def load_tokens():
    tokens_path = os.path.join(os.path.dirname(__file__), "tokens.json")
    try:
        with open(tokens_path, "r", encoding="utf-8") as f:
            tokens = json.load(f)
            if "access_token" not in tokens:
                print("access_token missing in tokens.json.")
                return None
            return tokens
    except FileNotFoundError:
        print(f"tokens.json not found at {tokens_path}.")
    except json.JSONDecodeError as e:
        print(f"JSON decode error in tokens.json: {e}")
    except Exception as e:
        print(f"Unexpected error loading tokens: {e}")
    return None

if __name__ == "__main__":
    # tokens = exchange_code_for_tokens(config.CODE_AUTH, config.CODE_CHALLENGE)

    tokens = refresh_token()

    if tokens:
        access_token = tokens.get("access_token")