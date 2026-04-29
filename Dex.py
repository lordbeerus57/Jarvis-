"""
╔══════════════════════════════════════════════════════════════╗
║           DIGIMON DEX BOT — Single File Edition             ║
║   Pyrogram + BeautifulSoup + JSON — No database needed      ║
╠══════════════════════════════════════════════════════════════╣
║  Install:                                                    ║
║    pip install pyrogram tgcrypto requests beautifulsoup4     ║
║                                                              ║
║  Run:                                                        ║
║    python bot.py                                             ║
╚══════════════════════════════════════════════════════════════╝

BOT COMMANDS (User):
  /dex <name or id>   — Look up a Digimon
  /random             — Random Digimon
  /list <page>        — Browse all Digimon (paginated)
  /search <query>     — Fuzzy search by name
  /type <type>        — Filter by type (e.g. Reptile, Dragon)
  /attribute <attr>   — Filter by attribute (Vaccine, Virus, Data)
  /generation <gen>   — Filter by generation/stage
  /compare <a> <b>    — Compare two Digimon stats
  /stats              — Dex database stats
  /help               — Show all commands

BOT COMMANDS (Admin only):
  /scrape             — Scrape all missing Digimon
  /scrapeall          — Force re-scrape everything
  /rescrape <slug>    — Re-scrape a single Digimon
  /dexstats           — Detailed database breakdown
  /exportjson         — Send the raw JSON file
  /importjson         — Reply to a JSON file to import it
  /deletemon <slug>   — Delete a Digimon from the dex
  /clearall           — ⚠️ Wipe entire dex (asks confirmation)
"""

import os
import re
import json
import time
import random
import asyncio
import logging
import requests
from pathlib import Path
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ══════════════════════════════════════════════
# ── CONFIGURATION — Edit these
# ══════════════════════════════════════════════
BOT_TOKEN  = "8380616064:AAHA9bWXBfxE9b3vqpfdiYGPa25eRYtdjfo"
API_ID     = 12400175     # From my.telegram.org
API_HASH   = "bd6cffecc030c99a2d23e2f9ff892c5f""
ADMIN_IDS  = [1214273889]  # Your Telegram user ID(s)

DEX_FILE      = "digimon_dex.json"
BASE_URL      = "https://www.grindosaur.com"
GAME_SLUG     = "digimon-story-time-stranger"
LIST_URL      = f"{BASE_URL}/en/games/{GAME_SLUG}/digimon/"
SCRAPE_DELAY  = 1.5   # seconds between requests
PAGE_SIZE     = 10    # Digimon per /list page

# ══════════════════════════════════════════════
# ── LOGGING
# ══════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("DigiDex")

# ══════════════════════════════════════════════
# ── JSON DEX STORAGE
# ══════════════════════════════════════════════
def load_dex() -> dict:
    path = Path(DEX_FILE)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_dex(dex: dict):
    with open(DEX_FILE, "w", encoding="utf-8") as f:
        json.dump(dex, f, ensure_ascii=False, indent=2)


def get_digimon(dex: dict, query: str) -> dict | None:
    """Search by ID (number) or name/slug (string)."""
    query = query.strip()

    # By numeric ID
    if query.isdigit():
        num = int(query)
        for d in dex.values():
            if d.get("id") == num:
                return d
        return None

    # Exact slug match
    slug = query.lower().replace(" ", "-")
    if slug in dex:
        return dex[slug]

    # Exact name match (case-insensitive)
    for d in dex.values():
        if d.get("name", "").lower() == query.lower():
            return d

    # Partial name match
    for d in dex.values():
        if query.lower() in d.get("name", "").lower():
            return d

    return None


def fuzzy_search(dex: dict, query: str, limit: int = 5) -> list[dict]:
    """Return top fuzzy matches sorted by similarity."""
    query = query.lower()
    scored = []
    for d in dex.values():
        name = d.get("name", "").lower()
        ratio = SequenceMatcher(None, query, name).ratio()
        if ratio > 0.4 or query in name:
            scored.append((ratio, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:limit]]


# ══════════════════════════════════════════════
# ── SCRAPER
# ══════════════════════════════════════════════
SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE_URL,
}

_session = requests.Session()
_session.headers.update(SCRAPE_HEADERS)


def _clean(text: str) -> str:
    return " ".join(text.split()).strip() if text else ""


def _get_soup(url: str) -> BeautifulSoup | None:
    try:
        r = _session.get(url, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log.warning(f"Fetch error {url}: {e}")
        return None


def scrape_slug_list() -> list[dict]:
    """Return list of {slug, id, url} for all Digimon."""
    soup = _get_soup(LIST_URL)
    if not soup:
        return []

    results = []
    seen = set()
    pattern = re.compile(rf"/en/games/{GAME_SLUG}/digimon/([^/\"'\s]+)/?$")

    for a in soup.find_all("a", href=True):
        m = pattern.search(a["href"])
        if not m:
            continue
        slug = m.group(1).strip("/")
        if not slug or slug in seen:
            continue
        seen.add(slug)

        id_match = re.match(r"(\d+)-(.+)", slug)
        results.append({
            "slug": slug,
            "id": int(id_match.group(1)) if id_match else None,
            "url": f"{BASE_URL}/en/games/{GAME_SLUG}/digimon/{slug}/",
        })

    results.sort(key=lambda x: (x["id"] or 9999, x["slug"]))
    return results


def scrape_digimon_page(slug: str, digimon_id: int | None, url: str) -> dict | None:
    """Scrape a single Digimon detail page."""
    soup = _get_soup(url)
    if not soup:
        return None

    data = {
        "id": digimon_id,
        "slug": slug,
        "url": url,
        "name": "",
        "image_url": "",
        "type": "",
        "attribute": "",
        "generation": "",
        "memory_cost": None,
        "description": "",
        "stats": {},
        "moves": [],
        "evolutions": {"from": [], "to": []},
    }

    # Name
    h1 = soup.find("h1")
    if h1:
        data["name"] = _clean(h1.get_text())

    # Image — og:image is most reliable
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        data["image_url"] = og["content"]
    else:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if src and re.search(r"\.(png|jpg|webp)", src, re.I):
                data["image_url"] = BASE_URL + src if src.startswith("/") else src
                break

    # Description
    for sel in [".description", ".lore", ".flavor-text", ".digimon-bio"]:
        el = soup.select_one(sel)
        if el:
            data["description"] = _clean(el.get_text())
            break
    if not data["description"]:
        for p in soup.find_all("p"):
            if p.find_parent("table"):
                continue
            txt = _clean(p.get_text())
            if len(txt) > 60:
                data["description"] = txt
                break

    # Info table (type, attribute, generation, memory)
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = _clean(cells[0].get_text()).lower()
        value = _clean(cells[1].get_text())
        if not value:
            continue
        if "type" in label and not data["type"]:
            data["type"] = value
        elif "attribute" in label and not data["attribute"]:
            data["attribute"] = value
        elif ("generation" in label or "stage" in label) and not data["generation"]:
            data["generation"] = value
        elif "memory" in label and data["memory_cost"] is None:
            m = re.search(r"\d+", value)
            if m:
                data["memory_cost"] = int(m.group())

    # Stats
    stat_map = {"hp": "HP", "atk": "ATK", "def": "DEF",
                "int": "INT", "spi": "SPI", "spd": "SPD"}
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = _clean(cells[0].get_text()).lower().replace(" ", "")
        for key, canon in stat_map.items():
            if key == label and canon not in data["stats"]:
                nums = re.findall(r"\d+", _clean(cells[-1].get_text()))
                if nums:
                    data["stats"][canon] = int(nums[0])

    # Moves
    for table in soup.find_all("table"):
        ths = [_clean(th.get_text()).lower() for th in table.find_all("th")]
        if not any(h in ths for h in ["move", "skill", "name", "attack"]):
            continue
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            move = {
                "name":    _clean(cells[0].get_text()),
                "type":    _clean(cells[1].get_text()) if len(cells) > 1 else "",
                "power":   _clean(cells[2].get_text()) if len(cells) > 2 else "",
                "sp_cost": _clean(cells[3].get_text()) if len(cells) > 3 else "",
            }
            if move["name"] and move["name"].lower() not in ("name", "move", "skill", "attack"):
                data["moves"].append(move)

    # Evolutions
    for section in soup.find_all(["section", "div"], class_=re.compile(
            r"digivol|evolut|digimon-from|digimon-to", re.I)):
        hx = section.find(re.compile(r"h[1-6]"))
        heading = _clean(hx.get_text()).lower() if hx else ""
        names = [_clean(a.get_text()) for a in section.find_all("a") if _clean(a.get_text())]
        if any(k in heading for k in ["from", "pre", "devolve", "previous"]):
            data["evolutions"]["from"].extend(names)
        elif any(k in heading for k in ["to", "next", "digivolves", "into"]):
            data["evolutions"]["to"].extend(names)

    data["evolutions"]["from"] = list(dict.fromkeys(data["evolutions"]["from"]))
    data["evolutions"]["to"]   = list(dict.fromkeys(data["evolutions"]["to"]))

    return data


async def run_scrape(progress_msg: Message, force: bool = False) -> tuple[int, int, int]:
    """
    Scrape all Digimon. Runs in executor so it doesn't block the bot.
    Returns (added, skipped, failed).
    """
    loop = asyncio.get_event_loop()

    def _scrape_sync():
        slugs = scrape_slug_list()
        if not slugs:
            return 0, 0, 0

        dex = load_dex()
        added = skipped = failed = 0

        for i, item in enumerate(slugs, 1):
            slug = item["slug"]

            if not force and slug in dex:
                skipped += 1
                continue

            log.info(f"[{i}/{len(slugs)}] {slug}")
            result = scrape_digimon_page(slug, item["id"], item["url"])

            if result and result.get("name"):
                dex[slug] = result
                added += 1
            else:
                failed += 1

            # Update progress every 25
            if i % 25 == 0:
                asyncio.run_coroutine_threadsafe(
                    progress_msg.edit_text(
                        f"⏳ Scraping… {i}/{len(slugs)}\n"
                        f"✅ Added: {added} | ⏭ Skipped: {skipped} | ❌ Failed: {failed}"
                    ),
                    loop
                )
                save_dex(dex)

            time.sleep(SCRAPE_DELAY)

        save_dex(dex)
        return added, skipped, failed

    return await loop.run_in_executor(None, _scrape_sync)


async def run_rescrape(slug: str) -> dict | None:
    """Re-scrape a single Digimon and update the dex."""
    loop = asyncio.get_event_loop()

    def _sync():
        url = f"{BASE_URL}/en/games/{GAME_SLUG}/digimon/{slug}/"
        id_match = re.match(r"(\d+)-", slug)
        digimon_id = int(id_match.group(1)) if id_match else None
        return scrape_digimon_page(slug, digimon_id, url)

    result = await loop.run_in_executor(None, _sync)
    if result and result.get("name"):
        dex = load_dex()
        dex[slug] = result
        save_dex(dex)
    return result


# ══════════════════════════════════════════════
# ── FORMATTERS
# ══════════════════════════════════════════════
STAT_BARS = {
    range(0,   50):  "▱▱▱▱▱",
    range(50,  100): "▰▱▱▱▱",
    range(100, 150): "▰▰▱▱▱",
    range(150, 200): "▰▰▰▱▱",
    range(200, 250): "▰▰▰▰▱",
    range(250, 999): "▰▰▰▰▰",
}

def stat_bar(value: int | None) -> str:
    if value is None:
        return "—"
    for r, bar in STAT_BARS.items():
        if value in r:
            return f"{bar} {value}"
    return f"▰▰▰▰▰ {value}"


def format_dex_card(d: dict) -> str:
    name  = d.get("name", "Unknown")
    did   = f"#{d['id']:03d}" if d.get("id") else "—"
    gen   = d.get("generation") or "—"
    typ   = d.get("type") or "—"
    attr  = d.get("attribute") or "—"
    mem   = str(d.get("memory_cost")) if d.get("memory_cost") else "—"
    desc  = d.get("description") or ""
    stats = d.get("stats", {})

    evos_from = ", ".join(d.get("evolutions", {}).get("from", [])) or "—"
    evos_to   = ", ".join(d.get("evolutions", {}).get("to",   [])) or "—"

    text = (
        f"🦖 **{name}** `{did}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ **Generation:** {gen}\n"
        f"🔷 **Type:** {typ}\n"
        f"🌀 **Attribute:** {attr}\n"
        f"💾 **Memory:** {mem}\n\n"
    )

    if stats:
        text += (
            f"📊 **Stats**\n"
            f"❤️ HP   {stat_bar(stats.get('HP'))}\n"
            f"⚔️ ATK  {stat_bar(stats.get('ATK'))}\n"
            f"🛡 DEF  {stat_bar(stats.get('DEF'))}\n"
            f"🔮 INT  {stat_bar(stats.get('INT'))}\n"
            f"✨ SPI  {stat_bar(stats.get('SPI'))}\n"
            f"💨 SPD  {stat_bar(stats.get('SPD'))}\n\n"
        )

    if desc:
        text += f"📖 _{desc[:300]}{'…' if len(desc) > 300 else ''}_\n\n"

    text += (
        f"🔄 **Digivolves from:** {evos_from}\n"
        f"⬆️ **Digivolves to:** {evos_to}\n"
    )

    return text


def dex_card_buttons(d: dict) -> InlineKeyboardMarkup:
    slug = d.get("slug", "")
    rows = []

    # Moves button
    if d.get("moves"):
        rows.append([InlineKeyboardButton("⚔️ Moves / Skills", callback_data=f"moves:{slug}")])

    # Evolution buttons
    evo_from = d.get("evolutions", {}).get("from", [])
    evo_to   = d.get("evolutions", {}).get("to",   [])

    if evo_from:
        btns = []
        for name in evo_from[:3]:
            s = name.lower().replace(" ", "-").replace("(", "").replace(")", "")
            btns.append(InlineKeyboardButton(f"⬇️ {name}", callback_data=f"dex:{s}"))
        rows.append(btns)

    if evo_to:
        btns = []
        for name in evo_to[:3]:
            s = name.lower().replace(" ", "-").replace("(", "").replace(")", "")
            btns.append(InlineKeyboardButton(f"⬆️ {name}", callback_data=f"dex:{s}"))
        rows.append(btns)

    rows.append([
        InlineKeyboardButton("🔀 Random", callback_data="random"),
        InlineKeyboardButton("🌐 Wiki", url=d.get("url", BASE_URL)),
    ])

    return InlineKeyboardMarkup(rows)


def format_moves(d: dict) -> str:
    moves = d.get("moves", [])
    if not moves:
        return f"**{d['name']}** has no recorded moves."

    text = f"⚔️ **{d['name']} — Moves & Skills**\n━━━━━━━━━━━━━━━\n"
    for m in moves:
        text += f"\n🔹 **{m['name']}**"
        if m.get("type"):
            text += f"  [{m['type']}]"
        if m.get("power"):
            text += f"  💥 {m['power']}"
        if m.get("sp_cost"):
            text += f"  💠 SP: {m['sp_cost']}"
        text += "\n"
    return text


def format_compare(a: dict, b: dict) -> str:
    def s(d, k):
        return d.get("stats", {}).get(k) or 0

    def winner(va, vb):
        if va > vb: return "◀"
        if vb > va: return "▶"
        return "="

    text = (
        f"⚔️ **{a['name']}** vs **{b['name']}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
    )
    for stat in ["HP", "ATK", "DEF", "INT", "SPI", "SPD"]:
        va, vb = s(a, stat), s(b, stat)
        w = winner(va, vb)
        text += f"`{stat:3}` {va:>5}  {w}  {vb:<5}\n"

    total_a = sum(s(a, k) for k in ["HP","ATK","DEF","INT","SPI","SPD"])
    total_b = sum(s(b, k) for k in ["HP","ATK","DEF","INT","SPI","SPD"])
    w = winner(total_a, total_b)
    text += f"\n`TOT` {total_a:>5}  {w}  {total_b:<5}\n"

    if total_a > total_b:
        text += f"\n🏆 **{a['name']}** wins overall!"
    elif total_b > total_a:
        text += f"\n🏆 **{b['name']}** wins overall!"
    else:
        text += "\n🤝 It's a tie!"

    return text


# ══════════════════════════════════════════════
# ── BOT SETUP
# ══════════════════════════════════════════════
app = Client("digimon_dex_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def send_dex_card(target, d: dict):
    """Send Digimon card with image + inline buttons to a Message or CallbackQuery."""
    text    = format_dex_card(d)
    buttons = dex_card_buttons(d)
    img_url = d.get("image_url", "")

    # Determine whether target is a Message or CallbackQuery
    if isinstance(target, CallbackQuery):
        msg = target.message
        try:
            if img_url:
                await msg.reply_photo(img_url, caption=text, reply_markup=buttons)
            else:
                await msg.reply_text(text, reply_markup=buttons)
        except Exception:
            await msg.reply_text(text, reply_markup=buttons)
    else:
        try:
            if img_url:
                await target.reply_photo(img_url, caption=text, reply_markup=buttons)
            else:
                await target.reply_text(text, reply_markup=buttons)
        except Exception:
            await target.reply_text(text, reply_markup=buttons)


# ══════════════════════════════════════════════
# ── USER COMMANDS
# ══════════════════════════════════════════════

@app.on_message(filters.command("start"))
async def cmd_start(_, msg: Message):
    await msg.reply_text(
        "🦖 **Welcome to DigiDex Bot!**\n\n"
        "Your complete Digimon encyclopedia from Digimon Story: Time Stranger.\n\n"
        "🔍 `/dex Agumon` — Look up any Digimon\n"
        "🎲 `/random` — Discover a random Digimon\n"
        "📋 `/list` — Browse all Digimon\n"
        "🔎 `/search <name>` — Fuzzy search\n"
        "📊 `/stats` — Database info\n"
        "❓ `/help` — All commands\n\n"
        "_Use /help for the full command list._"
    )


@app.on_message(filters.command("help"))
async def cmd_help(_, msg: Message):
    text = (
        "📖 **DigiDex Bot — Commands**\n\n"
        "**🔍 Lookup**\n"
        "`/dex <name or #id>` — Full Digimon info\n"
        "`/random` — Random Digimon\n"
        "`/search <query>` — Fuzzy name search\n\n"
        "**📋 Browse**\n"
        "`/list [page]` — Paginated Digimon list\n"
        "`/type <type>` — Filter by type\n"
        "`/attribute <attr>` — Filter by attribute\n"
        "`/generation <gen>` — Filter by generation\n\n"
        "**⚔️ Tools**\n"
        "`/compare <a> | <b>` — Stat comparison\n"
        "`/stats` — Dex statistics\n\n"
    )
    if is_admin(msg.from_user.id):
        text += (
            "**🔧 Admin**\n"
            "`/scrape` — Scrape missing Digimon\n"
            "`/scrapeall` — Force re-scrape all\n"
     
