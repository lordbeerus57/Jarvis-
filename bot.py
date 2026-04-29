import asyncio
import re
import os
import json
import random

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== DUMMY CONFIG (FOR TESTING ONLY) =====
API_ID = 12400175
API_HASH="bd6cffecc030c99a2d23e2f9ff892c5f"
BOT_TOKEN = "8380616064:AAHA9bWXBfxE9b3vqpfdiYGPa25eRYtdjfo"

# ===== CONFIG =====
BASE_URL = "https://digimon.net"
GAME_SLUG = "cyber-sleuth"
DEX_FILE = "dex.json"

# ===== STORAGE =====
def load_dex():
    if not os.path.exists(DEX_FILE):
        return {}
    with open(DEX_FILE, "r") as f:
        return json.load(f)

def save_dex(data):
    with open(DEX_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ===== SAFE HELPER =====
def s(d, k):
    return d.get(k)

# ===== SCRAPER (PLACEHOLDER DATA) =====
def scrape_digimon_page(slug, digimon_id, url):
    return {
        "name": slug.title(),
        "slug": slug,
        "id": digimon_id,
        "generation": "Rookie",
        "type": "Vaccine",
        "attribute": "Fire",
        "memory_cost": random.randint(5, 20),
        "stats": {
            "HP": random.randint(100, 300),
            "ATK": random.randint(100, 300),
            "DEF": random.randint(100, 300),
            "INT": random.randint(100, 300),
            "SPD": random.randint(100, 300),
        },
        "moves": [
            {"name": "Fire Blast", "power": 120, "sp_cost": 10},
            {"name": "Claw Attack", "power": 80, "sp_cost": 5},
        ],
        "evolutions": {"from": [], "to": []},
        "url": url,
        "description": "A powerful Digimon."
    }

# ===== CORE =====
async def run_rescrape(slug: str):
    loop = asyncio.get_event_loop()

    def _sync():
        url = f"{BASE_URL}/en/games/{GAME_SLUG}/digimon/{slug}/"
        match = re.match(r"(\d+)-", slug)
        digimon_id = int(match.group(1)) if match else None
        return scrape_digimon_page(slug, digimon_id, url)

    result = await loop.run_in_executor(None, _sync)

    if result:
        dex = load_dex()
        dex[slug] = result
        save_dex(dex)

    return result

# ===== FORMAT =====
def format_card(d):
    return f"""🦖 {s(d,'name')}
⚡ Gen: {s(d,'generation')}
🔷 Type: {s(d,'type')}
🌀 Attr: {s(d,'attribute')}

❤️ HP: {s(d['stats'],'HP')}
⚔️ ATK: {s(d['stats'],'ATK')}
🛡 DEF: {s(d['stats'],'DEF')}
🔮 INT: {s(d['stats'],'INT')}
💨 SPD: {s(d['stats'],'SPD')}
"""

def buttons(d):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Moves", callback_data=f"moves:{d['slug']}")],
        [InlineKeyboardButton("🔀 Random", callback_data="random")]
    ])

def format_moves(d):
    text = f"⚔️ {d['name']} Moves:\n"
    for m in d["moves"]:
        text += f"\n🔹 {m['name']} 💥{m['power']} SP:{m['sp_cost']}"
    return text

# ===== BOT =====
app = Client(
    "digimon-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ===== COMMANDS =====
@app.on_message(filters.command("start"))
async def start(_, msg):
    await msg.reply("🤖 Digimon Bot Running!")

@app.on_message(filters.command("dex"))
async def dex(_, msg):
    if len(msg.command) < 2:
        return await msg.reply("Usage: /dex agumon")

    slug = msg.command[1].lower()
    data = await run_rescrape(slug)

    await msg.reply(
        format_card(data),
        reply_markup=buttons(data)
    )

@app.on_message(filters.command("random"))
async def random_cmd(_, msg):
    slug = random.choice(["agumon", "gabumon", "patamon"])
    data = await run_rescrape(slug)

    await msg.reply(
        format_card(data),
        reply_markup=buttons(data)
    )

# ===== CALLBACK =====
@app.on_callback_query()
async def cb(_, query):
    data = query.data

    if data == "random":
        slug = random.choice(["agumon", "gabumon", "patamon"])
        d = await run_rescrape(slug)

        await query.message.edit(
            format_card(d),
            reply_markup=buttons(d)
        )

    elif data.startswith("moves:"):
        slug = data.split(":")[1]
        dex = load_dex()
        d = dex.get(slug) or await run_rescrape(slug)

        await query.message.edit(format_moves(d))

# ===== RUN =====
if __name__ == "__main__":
    print("🚀 Bot running...")
    app.run()
