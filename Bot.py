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
        f"🦖 {name} {did}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Generation: {gen}\n"
        f"🔷 Type: {typ}\n"
        f"🌀 Attribute: {attr}\n"
        f"💾 Memory: {mem}\n\n"
    )

    if stats:
        text += (
            f"📊 Stats\n"
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
        f"🔄 Digivolves from: {evos_from}\n"
        f"⬆️ Digivolves to: {evos_to}\n"
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
        return f"{d['name']} has no recorded moves."

    text = f"⚔️ {d['name']} — Moves & Skills\n━━━━━━━━━━━━━━━\n"
    for m in moves:
        text += f"\n🔹 {m['name']}"
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
