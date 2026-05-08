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
    TELEGRAM_CHAT_ID: str   # comma-separated list of allowed Telegram user IDs

    @property
    def ALLOWED_CHAT_IDS(self) -> list[int]:
        """Parse comma-separated chat IDs into a list of ints."""
        return [int(x.strip()) for x in self.TELEGRAM_CHAT_ID.split(",") if x.strip()]

    GROQ_API_KEY: str = ""
    HF_TOKEN: str = ""

    # PostgreSQL Config
    POSTGRES_URL: str = "postgresql+asyncpg://user:password@localhost/yt_automation"

    # Engine Config
    TTS_PRIMARY_MODEL: str = "xtts-v2"
    TTS_FALLBACK_MODEL: str = "piper"
    WHISPER_MODEL: str = "base"
    
    # YouTube Config
    YOUTUBE_CLIENT_SECRET_FILE: str = os.path.join("credentials", "client_secret.json")
    YOUTUBE_SCOPES: list = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly"
    ]

    # Paths
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    OUTPUT_DIR: str = os.path.join(BASE_DIR, "outputs")
    TEMP_DIR: str = os.path.join(BASE_DIR, "temp")
    ASSETS_DIR: str = os.path.join(BASE_DIR, "assets")
    CREDENTIALS_DIR: str = os.path.join(BASE_DIR, "credentials")

    # App Config
    DEFAULT_LANGUAGE: str = "ta"
    SIMILARITY_THRESHOLD: float = 0.7
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

# Ensure directories exist
os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
os.makedirs(settings.TEMP_DIR, exist_ok=True)
os.makedirs(settings.ASSETS_DIR, exist_ok=True)
os.makedirs(settings.CREDENTIALS_DIR, exist_ok=True)
