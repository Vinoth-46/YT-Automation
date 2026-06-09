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
        # Create new tables; existing ones are NOT modified by create_all
        await conn.run_sync(Base.metadata.create_all)
        # Safe-add new columns to existing tables (idempotent ALTER TABLE)
        await _safe_migrate(conn)
    logger.info("Database tables initialized")


async def _safe_migrate(conn):
    """Add new columns to existing tables without dropping data.
    Each ALTER TABLE is wrapped in a try/except so re-running is harmless.
    """
    migrations = [
        # (table, column, sql_type)
        ("jobs", "error_message", "TEXT"),
        ("jobs", "failed_stage",  "VARCHAR(64)"),
    ]
    for table, column, sql_type in migrations:
        try:
            await conn.execute(
                __import__("sqlalchemy").text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}"
                )
            )
            logger.info(f"Migration: ensured column {table}.{column} exists")
        except Exception as e:
            # Postgres: column already exists → ignore; any other error → log
            if "already exists" not in str(e).lower():
                logger.warning(f"Migration warning for {table}.{column}: {e}")
