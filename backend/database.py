import os
import ssl
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from .models import Base
from typing import AsyncGenerator
from dotenv import load_dotenv
load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# Convert postgres:// to postgresql:// for SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# For async operations, ensure we use asyncpg driver
ASYNC_DATABASE_URL = DATABASE_URL
if not ASYNC_DATABASE_URL.startswith("postgresql+asyncpg://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# For sync operations, ensure we use psycopg2 driver  
SYNC_DATABASE_URL = DATABASE_URL
if SYNC_DATABASE_URL.startswith("postgresql+asyncpg://"):
    SYNC_DATABASE_URL = SYNC_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

# SSL configuration for Docker
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Async engine for FastAPI (asyncpg uses 'ssl' parameter)
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "ssl": ssl_context
    }
)

# Sync engine for Celery workers (psycopg2 uses 'sslmode' parameter)
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "sslmode": "require"
    }
)

# Session makers
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False
)

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get async database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

def get_sync_db():
    """Get sync database session for Celery workers"""
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()

async def create_tables():
    """Create all tables with retry logic"""
    import asyncio
    
    max_retries = 3
    retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            async with async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print("Database tables created successfully!")
            return
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                print("All attempts failed. Could not create tables.")
                raise

def create_tables_sync():
    """Create all tables synchronously (for Celery workers)"""
    Base.metadata.create_all(bind=sync_engine)