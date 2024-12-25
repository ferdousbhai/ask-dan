import os
from datetime import date
import psycopg2
from psycopg2.extras import DictCursor

# Type hints for our credit data structure
CreditInfo = dict[str, dict[str, any]]

def is_production() -> bool:
    """Check if we're running in production (Railway)."""
    return bool(os.getenv('RAILWAY_STATIC_URL'))

def get_db_connection():
    """Get PostgreSQL connection if in production."""
    if not is_production():
        return None

    # Add error handling and connection string formatting
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set")

    # Railway provides PostgreSQL URLs starting with postgres://, but psycopg2 requires postgresql://
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)

    return psycopg2.connect(db_url)

def init_db():
    """Initialize the database table if it doesn't exist."""
    if not is_production():
        return

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_credits (
                    chat_id TEXT PRIMARY KEY,
                    username TEXT,
                    calls_remaining INTEGER,
                    last_reset DATE
                )
            """)
        conn.commit()

def load_credits() -> CreditInfo:
    """Load credits from PostgreSQL if in production."""
    if not is_production():
        return {}

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT * FROM user_credits")
            results = cur.fetchall()
            return {
                row['chat_id']: {
                    'username': row['username'],
                    'calls_remaining': row['calls_remaining'],
                    'last_reset': row['last_reset'].isoformat()
                }
                for row in results
            }

def save_credits(credits: CreditInfo) -> None:
    """Save credits to PostgreSQL if in production."""
    if not is_production():
        return

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for chat_id, info in credits.items():
                cur.execute("""
                    INSERT INTO user_credits (chat_id, username, calls_remaining, last_reset)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (chat_id)
                    DO UPDATE SET
                        username = EXCLUDED.username,
                        calls_remaining = EXCLUDED.calls_remaining,
                        last_reset = EXCLUDED.last_reset
                """, (
                    chat_id,
                    info['username'],
                    info['calls_remaining'],
                    info['last_reset']
                ))
        conn.commit()

def is_admin(username: str) -> bool:
    """Check if user is admin."""
    return username == os.getenv('ADMIN_USERNAME')

def reset_monthly_credits(credit_info: dict) -> dict:
    """Reset credits if it's a new month."""
    today = date.today().isoformat()
    last_reset = credit_info.get('last_reset', '')

    if not last_reset or last_reset[:7] != today[:7]:  # Compare year-month
        credit_info['calls_remaining'] = 10
        credit_info['last_reset'] = today

    return credit_info

def check_credits(chat_id: str, username: str) -> tuple[bool, str]:
    """
    Check if user has enough credits.
    Returns (bool, message) tuple.
    """
    # Skip credit check in local development
    if not is_production():
        return True, "Local development - no credit check"

    if is_admin(username):
        return True, "Admin has unlimited access"

    credits = load_credits()
    if chat_id not in credits:
        credits[chat_id] = {
            "username": username,
            "calls_remaining": 10,
            "last_reset": date.today().isoformat()
        }

    credits[chat_id] = reset_monthly_credits(credits[chat_id])

    if credits[chat_id]["calls_remaining"] <= 0:
        return False, "You have no calls remaining this month. Resets on the 1st of next month."

    return True, f"You have {credits[chat_id]['calls_remaining']} calls remaining this month."

def deduct_credit(chat_id: str, username: str) -> None:
    """Deduct one credit from user's balance."""
    if not is_production() or is_admin(username):
        return

    credits = load_credits()
    if chat_id in credits:
        credits[chat_id]["calls_remaining"] -= 1
        save_credits(credits)

def get_user_credits(chat_id: str) -> dict | None:
    """Get credit info for a specific user."""
    if not is_production():
        return {"calls_remaining": "∞", "last_reset": date.today().isoformat()}
    credits = load_credits()
    return credits.get(chat_id)

def get_all_credits() -> CreditInfo:
    """Get all users' credits."""
    if not is_production():
        return {"local": {"calls_remaining": "∞", "last_reset": date.today().isoformat()}}
    return load_credits()

def set_user_credits(chat_id: str, amount: int) -> None:
    """Set credits for a specific user."""
    if not is_production():
        return
    credits = load_credits()
    if chat_id in credits:
        credits[chat_id]["calls_remaining"] = amount
        save_credits(credits)

def reset_all_credits() -> None:
    """Reset all users' credits to 10."""
    if not is_production():
        return
    credits = load_credits()
    today = date.today().isoformat()
    for chat_id in credits:
        credits[chat_id]["calls_remaining"] = 10
        credits[chat_id]["last_reset"] = today
    save_credits(credits)

# Initialize database table when module is loaded
if is_production():
    init_db()