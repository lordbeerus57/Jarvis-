"""
Run this ONCE on the server to generate and save your session string.
It will save to session.env which jarvis_ghost.py will auto-load.

Usage:
    python setup_session.py
"""

import os
import asyncio
from pyrogram import Client

SESSION_FILE = "session.env"

async def main():
    print("\n⚡ JARVIS SESSION SETUP")
    print("=" * 40)

    api_id   = input("Enter API_ID: ").strip()
    api_hash = input("Enter API_HASH: ").strip()

    print("\n📱 Telegram will send you an OTP code...")

    async with Client(
        "temp_setup",
        api_id=int(api_id),
        api_hash=api_hash,
    ) as app:
        session_string = await app.export_session_string()

    # Save to session.env
    with open(SESSION_FILE, "w") as f:
        f.write(f'API_ID={api_id}\n')
        f.write(f'API_HASH={api_hash}\n')
        f.write(f'SESSION_STRING={session_string}\n')

    # Clean up temp session file
    for f in ["temp_setup.session", "temp_setup.session-journal"]:
        if os.path.exists(f):
            os.remove(f)

    print("\n✅ Session saved to session.env")
    print("🚀 Now run: python jarvis_ghost.py")

if __name__ == "__main__":
    asyncio.run(main())
