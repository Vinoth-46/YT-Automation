from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .config import settings
import logging
import ssl

logger = logging.getLogger(__name__)

class Database:
    engine = None
    async_session = None

    @classmethod
    def connect(cls):
        try:
            # Create SSL context for Supabase connection
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            cls.engine = create_async_engine(
                settings.POSTGRES_URL,
                echo=False,
                future=True,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=300,
                connect_args={
                    "ssl": ssl_context,
                    "server_settings": {
                        "application_name": "yt-automation"
                    }
                }
            )
            cls.async_session = async_sessionmaker(
                cls.engine, 
                expire_on_commit=False, 
                class_=AsyncSession
            )
            logger.info(f"Successfully configured PostgreSQL connection")
        except Exception as e:
            logger.error(f"Could not configure PostgreSQL: {e}")
            raise

    @classmethod
    async def close(cls):
        if cls.engine:
            await cls.engine.dispose()
            logger.info("PostgreSQL connection closed")

    @classmethod
    def get_session(cls) -> AsyncSession:
        if cls.async_session is None:
            raise RuntimeError("Database not initialized. Call Database.connect() first.")
        return cls.async_session()

# Database initialization helper
async def init_db():
    from .models import Base
    Database.connect()
    async with Database.engine.begin() as conn:
        # This will create tables if they don't exist
        # In production, use Alembic for migrations
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")
