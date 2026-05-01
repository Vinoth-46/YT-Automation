import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_db

async def main():
    print("Initializing database on Supabase...")
    try:
        await init_db()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Failed to initialize database: {e}")

if __name__ == "__main__":
    asyncio.run(main())
