from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .config import settings
import logging

logger = logging.getLogger(__name__)

class Database:
    engine = None
    async_session = None

    @classmethod
    def connect(cls):
        try:
            cls.engine = create_async_engine(
                settings.POSTGRES_URL,
                echo=False,
                future=True,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True
            )
            cls.async_session = async_sessionmaker(
                cls.engine, 
                expire_on_commit=False, 
                class_=AsyncSession
            )
            logger.info("Successfully configured PostgreSQL connection")
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
