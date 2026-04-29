import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # API Keys
    OPENROUTER_API_KEY: str
    PEXELS_API_KEY: str
    GEMINI_API_KEY: str
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: int
    HF_TOKEN: str = ""

    # MongoDB Config
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "yt_automation"

    # Paths
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    OUTPUT_DIR: str = os.path.join(BASE_DIR, "outputs")
    TEMP_DIR: str = os.path.join(BASE_DIR, "temp")
    ASSETS_DIR: str = os.path.join(BASE_DIR, "assets")

    # App Config
    DEFAULT_LANGUAGE: str = "ta"  # Tamil
    VOICE_PROFILE: str = "Puck"  # Gemini voice name (placeholder)
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

# Ensure directories exist
os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
os.makedirs(settings.TEMP_DIR, exist_ok=True)
os.makedirs(settings.ASSETS_DIR, exist_ok=True)
