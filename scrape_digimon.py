"""
Digimon Dex Scraper — game8.co (Time Stranger)
================================================
Install deps:
    pip install playwright
    playwright install chromium

Run:
    python scrape_digimon.py

Output: digimon.json  (put it in same folder as your bot)
"""

import asyncio
import json
import re
from playwright.async_api import async_playwright

BASE = "https://game8.co"

GEN_PAGES = [
    ("In-Training I",  "/games/Digimon-Story-Time-Stranger/archives/556242"),
    ("In-Training II", "/games/Digimon-Story-Time-Stranger/archives/556271"),
    ("Rookie",         "/games/Digimon-Story-Time-Stranger/archives/556272"),
    ("Champion",       "/games/Digimon-Story-Time-Stranger/archives/556273"),
    ("Ultimate",       "/games/Digimon-Story-Time-Stranger/archives/556274"),
    ("Mega",           "/games/Digimon-Story-Time-Stranger/archives/556275"),
    ("Mega+",          "/games/Digimon-Story-Time-Stranger/archives/556276"),
    ("Armor",          "/games/Digimon-Story-Time-Stranger/archives/556277"),
    ("Hybrid",         "/games/Digimon-Story-Time-Stranger/archives/556278"),
]

ATTRIBUTES = ["Vaccine", "Data", "Virus", "Free", "Variable", "Unknown", "No Data"]


async def get_digimon_links(page, gen_name, path):
    url = BASE + path
    print(f"\n📖 [{gen_name}] {url}")
    await page.goto(url, wait_until="networkidle", timeout=60000)

    try:
        await page.wait_for_selector("table", timeout=15000)
    except Exception:
        print(f"  ⚠ No table found")
        return []

    entries = []
    rows = await page.query_selector_all("table tr")

    for row in rows:
        cells = await row.query_selector_all("td")
        if not cells:
            continue

        link_el = None
        for cell in cells:
            link_el = await cell.query_selector("a[href*='/archives/']")
            if link_el:
                break
        if not link_el:
            continue

        name = (await link_el.inner_text()).strip()
        href = await link_el.get_attribute("href") or ""
        if not name or not href:
            continue

        attribute = "Unknown"
        for cell in cells:
            txt = (await cell.inner_text()).strip()
            for attr in ATTRIBUTES:
                if attr.lower() in txt.lower():
                    attribute = attr
                    break

        img_url = ""
        for cell in cells:
            img_el = await cell.query_selector("img")
            if img_el:
                src = await img_el.get_attribute("src") or ""
                if not src.startswith("data:"):
                    img_url = src
                else:
                    src = await img_el.get_attribute("data-src") or ""
                    if src and not src.startswith("data:"):
                        img_url = src
                if img_url:
                    break

        entries.append({
            "name": name,
            "generation": gen_name,
            "attribute": attribute,
            "image": img_url,
            "detail_url": BASE + href if href.startswith("/") else href,
            "stats": {},
            "skills": [],
            "evolves_from": [],
            "evolves_to": [],
        })

    print(f"  ✓ {len(entries)} Digimon found")
    return entries


async def scrape_detail(page, entry):
    url = entry["detail_url"]
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(0.8)
    except Exception as e:
        print(f"  ✗ {entry['name']}: {e}")
        return entry

    # Real image
    if not entry["image"]:
        for sel in ["article img", ".archive-img img", "img[src*='game8']"]:
            img_el = await page.query_selector(sel)
            if img_el:
                src = await img_el.get_attribute("src") or ""
                if src and not src.startswith("data:"):
                    entry["image"] = src
                    break

    # Stats
    stat_keys = ["HP", "SP", "ATK", "DEF", "INT", "SPI", "SPD", "ABI"]
    rows = await page.query_selector_all("table tr")
    for row in rows:
        cells = await row.query_selector_all("td, th")
        if len(cells) < 2:
            continue
        label = (await cells[0].inner_text()).strip()
        value = (await cells[1].inner_text()).strip()
        for sk in stat_keys:
            if label.strip() == sk or label.startswith(sk + " "):
                num = re.sub(r"[^\d]", "", value)
                if num:
                    entry["stats"][sk] = int(num)
        if any(x in label for x in ["Attribute", "Type"]):
            for attr in ATTRIBUTES:
                if attr.lower() in value.lower():
                    entry["attribute"] = attr

    # Skills
    headings = await page.query_selector_all("h2, h3, h4")
    for heading in headings:
        h_text = (await heading.inner_text()).strip().lower()
        if "skill" not in h_text:
            continue
        table = await heading.evaluate_handle("""el => {
            let next = el.nextElementSibling;
            while (next && next.tagName !== 'TABLE') next = next.nextElementSibling;
            return next;
        }""")
        if not table:
            continue
        skill_rows = await table.query_selector_all("tr")
        for sr in skill_rows:
            cells = await sr.query_selector_all("td")
            if len(cells) >= 1:
                skill_name = (await cells[0].inner_text()).strip()
                desc = (await cells[1].inner_text()).strip() if len(cells) > 1 else ""
                sp_cost = (await cells[2].inner_text()).strip() if len(cells) > 2 else ""
                if skill_name and "name" not in skill_name.lower():
                    entry["skills"].append({
                        "name": skill_name,
                        "description": desc,
                        "sp_cost": sp_cost,
                    })

    # Evolutions
    for heading in headings:
        h_text = (await heading.inner_text()).strip().lower()
        if "evolution" not in h_text and "digivol" not in h_text:
            continue
        table = await heading.evaluate_handle("""el => {
            let next = el.nextElementSibling;
            while (next && next.tagName !== 'TABLE') next = next.nextElementSibling;
            return next;
        }""")
        if not table:
            continue
        links = await table.query_selector_all("a")
        for link in links:
            evo_name = (await link.inner_text()).strip()
            if evo_name and evo_name != entry["name"]:
                if evo_name not in entry["evolves_to"]:
                    entry["evolves_to"].append(evo_name)

    print(f"  ✓ {entry['name']} | stats: {list(entry['stats'].keys())} | skills: {len(entry['skills'])}")
    return entry


async def main():
    all_digimon = []
    seen = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await ctx.new_page()

        print("=" * 50)
        print("STEP 1: Collecting Digimon from generation pages")
        print("=" * 50)
        for gen_name, path in GEN_PAGES:
            entries = await get_digimon_links(page, gen_name, path)
            for e in entries:
                if e["name"] not in seen:
                    seen.add(e["name"])
                    all_digimon.append(e)

        print(f"\n✅ Total unique Digimon: {len(all_digimon)}")

        print("\n" + "=" * 50)
        print("STEP 2: Scraping detail pages")
        print("=" * 50)
        for i, entry in enumerate(all_digimon):
            print(f"[{i+1}/{len(all_digimon)}] {entry['name']}")
            await scrape_detail(page, entry)
            await asyncio.sleep(0.5)

        await browser.close()

    # Save indexed by lowercase name for fast bot lookup
    dex = {d["name"].lower(): d for d in all_digimon}
    with open("digimon.json", "w", encoding="utf-8") as f:
        json.dump(dex, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 Saved {len(dex)} Digimon to digimon.json")


if __name__ == "__main__":
    asyncio.run(main())
                                      
