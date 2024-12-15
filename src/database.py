import os
from contextlib import asynccontextmanager
from datetime import datetime
import logging
import aiosqlite
from src.model import MemoryState

# Set database path
IS_RAILWAY = os.getenv('RAILWAY_ENVIRONMENT') is not None
if IS_RAILWAY:
    DATABASE_PATH = '/data/bot_memory.db'
else:
    # For local development, use a directory in the project
    DATABASE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'bot_memory.db')

async def init_db():
    """Initialize the database with required tables."""
    try:
        # Create data directory if it doesn't exist (local development only)
        if not IS_RAILWAY:
            os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        
        async with get_db() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chat_memories (
                    chat_id TEXT PRIMARY KEY,
                    memory_content TEXT,
                    created_at TEXT
                )
            """)
            await db.commit()
    except Exception as e:
        logging.error(f"Database initialization error: {e}")
        raise

@asynccontextmanager
async def get_db():
    """Async context manager for database connections."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        yield db

async def save_memory(chat_id: int, memory_state: MemoryState):
    """Save or update memory state for a chat."""
    try:
        async with get_db() as db:
            await db.execute("""
                INSERT OR REPLACE INTO chat_memories (chat_id, memory_content, created_at)
                VALUES (?, ?, ?)
            """, (
                str(chat_id),
                memory_state.memory_content,
                memory_state.created_at.isoformat()
            ))
            await db.commit()
    except Exception as e:
        logging.exception("Error saving memory to database")
        raise e

async def get_memory(chat_id: int) -> MemoryState | None:
    """Retrieve memory state for a chat."""
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT memory_content, created_at FROM chat_memories WHERE chat_id = ?",
                (str(chat_id),)
            ) as cursor:
                if row := await cursor.fetchone():
                    return MemoryState(
                        memory_content=row[0],
                        created_at=datetime.fromisoformat(row[1])
                    )
        return None
    except Exception as e:
        logging.exception("Error retrieving memory from database")
        raise e