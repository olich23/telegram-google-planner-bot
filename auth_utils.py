import os
import base64
import pickle
import io
import logging
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]

def get_credentials():
    creds = None
    encoded_token = os.getenv("GOOGLE_TOKEN")
    if encoded_token:
        try:
            token_data = base64.b64decode(encoded_token)
            creds = pickle.load(io.BytesIO(token_data))
        except Exception as e:
            logging.error(f"Ошибка загрузки токена: {e}")

    if not creds:
        flow = InstalledAppFlow.from_client_config(
            eval(os.getenv("GOOGLE_CREDENTIALS")), SCOPES
        )
        creds = flow.run_local_server(port=0)
    return creds
