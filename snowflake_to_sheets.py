import os
import json
import requests
import time
import jwt
import gspread
from google.oauth2.service_account import Credentials
from cryptography.hazmat.primitives import serialization

# --- Secrets GitHub Actions ---
PRIVATE_KEY = os.environ['SNOWFLAKE_PRIVATE_KEY']
PASSPHRASE = os.environ['SNOWFLAKE_PASSPHRASE']
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']

# --- Paramètres à adapter directement dans le code ---
USER = "PROD_CS_WRB"
ACCOUNT = "PAYFIT-DATA"
ACCOUNT_URL = "PAYFIT-DATA.snowflakecomputing.com"
WAREHOUSE = "ANALYSIS"
ROLE = "PROD_CS_WRB"
DATABASE = "RAW_PROD"
SCHEMA = "PUBLIC"
SQL = "SELECT * FROM raw_prod.staging_dust.assistant_messages LIMIT 10"
GOOGLE_SHEET_ID = "1jtOe8g5Bkgv02TFp9AZi101SDJJ5NNMtGJQqmCYInBU"  # Mets ici l'ID de ton Google Sheet

# --- Authentification Google Sheets via secret JSON ---
SERVICE_ACCOUNT_INFO = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
creds = Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO, 
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
gc = gspread.authorize(creds)
sh = gc.open_by_key(GOOGLE_SHEET_ID)
worksheet = sh.worksheet('Test MAN')  # Modifie si besoin

# --- Décrypter la clé privée chiffrée ---
private_key_obj = serialization.load_pem_private_key(
    PRIVATE_KEY.encode("utf-8"),
    password=PASSPHRASE.encode("utf-8"),
)

private_key_decrypted = private_key_obj.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

# --- Générer JWT pour Snowflake ---
now = int(time.time())
payload = {
    "iss": f"{ACCOUNT}.snowflakecomputing.com:{USER}",
    "sub": f"{ACCOUNT}.snowflakecomputing.com:{USER}",
    "aud": f"https://{ACCOUNT_URL}/oauth/token-request",
    "iat": now,
    "exp": now + 300
}

jwt_token = jwt.encode(
    payload,
    private_key_decrypted,
    algorithm='RS256'
)

# --- Obtenir l'access_token Snowflake ---
token_url = f"https://{ACCOUNT_URL}/oauth/token-request"
resp = requests.post(token_url, data={
    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
    "assertion": jwt_token
})
print("Réponse Snowflake :", resp.text)
resp.raise_for_status()
access_token = resp.json()['access_token']

# --- Exécuter la requête SQL ---
body = {
    "statement": SQL,
    "timeout": 60,
    "warehouse": WAREHOUSE,
    "database": DATABASE,
    "schema": SCHEMA,
    "role": ROLE,
    "resultSetMetaData": { "format": "json" }
}
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}
api_url = f"https://{ACCOUNT_URL}/api/v2/statements"
api_resp = requests.post(api_url, json=body, headers=headers)
api_resp.raise_for_status()
result = api_resp.json()
columns = [col['name'] for col in result['resultSetMetaData']['rowType']]
data = result['data']
output = [columns] + data

worksheet.clear()
worksheet.update('A1', output)
print("✅ Données Snowflake écrites dans Google Sheets")
