#!/usr/bin/env python3
"""
Script to initialize database tables
"""
import asyncio
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.database import create_tables

async def main():
    """Initialize database tables"""
    print("Creating database tables...")
    await create_tables()
    print("Database tables created successfully!")

if __name__ == "__main__":
    asyncio.run(main())