"""
Digimon Dex Bot — Pyrogram
===========================
Install:
    pip install pyrogram tgcrypto

Place digimon.json in the same folder, then run:
    python dex_bot.py

Commands:
    /dex <name>   — show Digimon card with inline buttons
    /search <q>   — search by partial name
"""

import json
import os
from difflib import get_close_matches

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
)

# ── Config ───────────────────────────────────────────────────
API_ID   = 12400175         # your api_id
API_HASH = "bd6cffecc030c99a2d23e2f9ff892c5f"          # your api_hash
BOT_TOKEN = "8380616064:AAHA9bWXBfxE9b3vqpfdiYGPa25eRYtdjfo"         # your bot token

# ── Load dex ─────────────────────────────────────────────────
with open("digimon.json", "r", encoding="utf-8") as f:
    DEX: dict = json.load(f)   # key = lowercase name

ALL_NAMES = list(DEX.keys())   # for search

app = Client("digimon_dex", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ── Attribute emojis & stat bars ─────────────────────────────
ATTR_EMOJI = {
    "Vaccine":  "💉",
    "Data":     "💾",
    "Virus":    "☣️",
    "Free":     "🌀",
    "Variable": "🔮",
    "Unknown":  "❓",
    "No Data":  "⬛",
}

GEN_EMOJI = {
    "In-Training I":  "🥚",
    "In-Training II": "🐣",
    "Rookie":         "⚡",
    "Champion":       "🔥",
    "Ultimate":       "💥",
    "Mega":           "👑",
    "Mega+":          "🌟",
    "Armor":          "🛡️",
    "Hybrid":         "⚙️",
}

STAT_MAX = {"HP": 4000, "SP": 1000, "ATK": 1000, "DEF": 1000,
            "INT": 1000, "SPI": 1000, "SPD": 400, "ABI": 200}

def stat_bar(value: int, stat: str) -> str:
    max_val = STAT_MAX.get(stat, 1000)
    filled = round((value / max_val) * 10)
    filled = max(0, min(10, filled))
    return "█" * filled + "░" * (10 - filled)


# ── Card builder ─────────────────────────────────────────────
def build_card(data: dict, page: str = "main") -> tuple[str, InlineKeyboardMarkup]:
    name  = data["name"]
    gen   = data.get("generation", "?")
    attr  = data.get("attribute", "Unknown")
    stats = data.get("stats", {})
    skills = data.get("skills", [])
    evo_to = data.get("evolves_to", [])
    evo_from = data.get("evolves_from", [])
    key   = name.lower()

    gen_icon  = GEN_EMOJI.get(gen, "•")
    attr_icon = ATTR_EMOJI.get(attr, "•")

    # ── MAIN page ────────────────────────────────────────────
    if page == "main":
        lines = [
            f"**╔══『 {name.upper()} 』══╗**",
            f"",
            f"{gen_icon} **Generation:** `{gen}`",
            f"{attr_icon} **Attribute:** `{attr}`",
            f"",
        ]
        if stats:
            lines.append("**【 BASE STATS 】**")
            for stat, val in stats.items():
                bar = stat_bar(val, stat)
                lines.append(f"`{stat:<3}` {bar} `{val}`")
        else:
            lines.append("_Stats not yet available_")

        lines += ["", f"**╚{'═' * (len(name) + 8)}╝**"]
        text = "\n".join(lines)

        buttons = []
        row1 = []
        if skills:
            row1.append(InlineKeyboardButton("⚔️ Skills", callback_data=f"dex|{key}|skills"))
        if evo_to or evo_from:
            row1.append(InlineKeyboardButton("🔄 Evolutions", callback_data=f"dex|{key}|evo"))
        if row1:
            buttons.append(row1)

        source = data.get("detail_url", "")
        if source:
            buttons.append([InlineKeyboardButton("🌐 game8 page", url=source)])

        return text, InlineKeyboardMarkup(buttons) if buttons else None

    # ── SKILLS page ──────────────────────────────────────────
    elif page == "skills":
        lines = [f"**⚔️ {name} — Skills**", ""]
        if not skills:
            lines.append("_No skills data available_")
        else:
            for s in skills[:10]:  # cap at 10 to avoid message limit
                sp = f" _(SP: {s['sp_cost']})_" if s.get("sp_cost") else ""
                lines.append(f"▸ **{s['name']}**{sp}")
                if s.get("description"):
                    lines.append(f"  _{s['description']}_")
                lines.append("")

        text = "\n".join(lines)
        buttons = [[InlineKeyboardButton("◀️ Back", callback_data=f"dex|{key}|main")]]
        return text, InlineKeyboardMarkup(buttons)

    # ── EVOLUTIONS page ───────────────────────────────────────
    elif page == "evo":
        lines = [f"**🔄 {name} — Evolution Line**", ""]
        if evo_from:
            lines.append("**Evolves From:**")
            for e in evo_from:
                lines.append(f"  `{e}`")
            lines.append("")
        if evo_to:
            lines.append("**Evolves To:**")
            for e in evo_to:
                lines.append(f"  `{e}`")
        if not evo_from and not evo_to:
            lines.append("_No evolution data available_")

        text = "\n".join(lines)
        # Buttons: quick-jump to each evolution that exists in dex
        evo_buttons = []
        for e in (evo_from + evo_to)[:6]:
            if e.lower() in DEX:
                evo_buttons.append(
                    InlineKeyboardButton(e, callback_data=f"dex|{e.lower()}|main")
                )
        rows = []
        for i in range(0, len(evo_buttons), 2):
            rows.append(evo_buttons[i:i+2])
        rows.append([InlineKeyboardButton("◀️ Back", callback_data=f"dex|{key}|main")])
        return text, InlineKeyboardMarkup(rows)

    return "Unknown page", None


# ── /dex command ──────────────────────────────────────────────
@app.on_message(filters.command("dex"))
async def cmd_dex(client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Usage: `/dex <digimon name>`\nExample: `/dex agumon`")
        return

    query = args[1].strip().lower()
    data = DEX.get(query)

    # fuzzy match if exact not found
    if not data:
        matches = get_close_matches(query, ALL_NAMES, n=5, cutoff=0.5)
        if not matches:
            await message.reply(f"❌ **{args[1]}** not found in the dex.")
            return
        if len(matches) == 1:
            data = DEX[matches[0]]
        else:
            # Show choice buttons
            buttons = [[InlineKeyboardButton(m.title(), callback_data=f"dex|{m}|main")]
                       for m in matches]
            await message.reply(
                f"❓ Did you mean one of these?",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

    text, markup = build_card(data, "main")
    image = data.get("image", "")

    if image and image.startswith("http"):
        await message.reply_photo(
            photo=image,
            caption=text,
            reply_markup=markup,
        )
    else:
        await message.reply(text, reply_markup=markup)


# ── /search command ───────────────────────────────────────────
@app.on_message(filters.command("search"))
async def cmd_search(client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Usage: `/search <partial name>`")
        return

    query = args[1].strip().lower()
    results = [n for n in ALL_NAMES if query in n][:10]

    if not results:
        await message.reply(f"❌ No Digimon found matching `{args[1]}`")
        return

    buttons = [[InlineKeyboardButton(n.title(), callback_data=f"dex|{n}|main")]
               for n in results]
    await message.reply(
        f"🔍 Found **{len(results)}** result(s) for `{args[1]}`:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ── Callback handler (inline button presses) ─────────────────
@app.on_callback_query(filters.regex(r"^dex\|"))
async def callback_dex(client, query: CallbackQuery):
    _, key, page = query.data.split("|", 2)
    data = DEX.get(key)

    if not data:
        await query.answer("Digimon not found!", show_alert=True)
        return

    text, markup = build_card(data, page)
    image = data.get("image", "")

    try:
        if page == "main" and image and image.startswith("http"):
            # If the current message has a photo, edit caption
            if query.message.photo:
                await query.message.edit_caption(caption=text, reply_markup=markup)
            else:
                await query.message.edit_text(text, reply_markup=markup)
        else:
            if query.message.photo:
                await query.message.edit_caption(caption=text, reply_markup=markup)
            else:
                await query.message.edit_text(text, reply_markup=markup)
    except Exception:
        await query.answer()

    await query.answer()


# ── Run ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🦕 Digimon Dex Bot running...")
    app.run()
    
