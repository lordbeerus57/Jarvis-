"""
Run this ONCE locally to generate your Pyrogram session string.
Then paste the output into Render as the SESSION_STRING env var.

Usage:
    pip install pyrogram TgCrypto
    python get_session.py
"""

from pyrogram import Client

API_ID   = input("Enter API_ID: ").strip()
API_HASH = input("Enter API_HASH: ").strip()

with Client("temp_session", api_id=int(API_ID), api_hash=API_HASH) as app:
    session = app.export_session_string()

print("\n" + "="*60)
print("YOUR SESSION STRING (paste into Render as SESSION_STRING):")
print("="*60)
print(session)
print("="*60)
print("\n⚠️  Keep this secret — it gives full access to your account!")
