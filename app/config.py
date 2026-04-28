import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN")
    BLING_ACCESS_TOKEN = os.getenv("BLING_ACCESS_TOKEN")
    BLING_REFRESH_TOKEN = os.getenv("BLING_REFRESH_TOKEN")
    BLING_CLIENT_ID = os.getenv("BLING_CLIENT_ID")
    BLING_CLIENT_SECRET = os.getenv("BLING_CLIENT_SECRET")
    DATABASE_URL = os.getenv("DATABASE_URL")

settings = Settings()