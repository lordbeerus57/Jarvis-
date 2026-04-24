import os
import subprocess
import asyncio
import json
import time
import hashlib
import logging
import re
from datetime import datetime
from pyrogram import Client, filters, types
from pyrogram.types import Message
from pydub import AudioSegment
import speech_recognition as sr
import ollama

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
API_ID         = int(os.getenv("API_ID", "12400175"))
API_HASH       = os.getenv("API_HASH", "bd6cffecc030c99a2d23e2f9ff892c5f")
SESSION_STRING = os.getenv("SESSION_STRING", "BQc9Ni8AQwZ8LUjwMeV13RCCaCDoBeJ6QzYy5CENB7Tdyfv8jR5zo5aU6H7gdK3xaYQ8qUqNgYp-19naCKlyd3FtsJaJ-aHM0-xa-x02YcJi4RYTxWGB5q4dWq3naBI9xH-cgN_MsZdRVgpI0_wfZBI8gfQ5acf00Szy8tp-UIAwkYGdBVt1PYmXcW1dLzPoaG605Kjohwo0zI08CmGP6Sor0JerISHp3I2PQv7ck8z0eqEGvrLlZ0rK2s0_jZNVIq3vVTIIQGc7YzPNVEM0d30rf8FWnVF0PLikrnMpLGm1k5chRVFW9bkKRpcq0duHjeRq-n9zaq6q8N3Z2_HzneTN0V1Y_wAAAABIYFlhAA")   # for Render (no local session file)
LOG_GROUP_ID   = int(os.getenv("LOG_GROUP_ID", "-1002798388984"))
MODEL          = os.getenv("JARVIS_MODEL", "gemma4:27b")
DEPLOY_DIR     = os.getenv("DEPLOY_DIR", "/opt/bots")
VENV_PYTHON    = os.getenv("VENV_PYTHON", "python3")
REGISTRY_FILE  = os.path.join(DEPLOY_DIR, "registry.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("Jarvis")

# Use session string if available (Render), else local session file
app = Client(
    name="jarvis_ghost_session",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING if SESSION_STRING else None,
)

recognizer    = sr.Recognizer()
pending_orders: dict = {}
running_bots:  dict = {}

os.makedirs(DEPLOY_DIR, exist_ok=True)

HELP_TEXT = """
🤖 **JARVIS GHOST SERVER**
_Voice-controlled Telegram userbot_

━━━━━━━━━━━━━━━━━━━━━
**📋 TEXT COMMANDS**
━━━━━━━━━━━━━━━━━━━━━
`.help` — Show this message
`.ping` — Latency check
`.status` — Running bots
`.registry` — Registered bots
`.log <id>` — Bot log tail
`.stop <id>` — Stop a bot
`.stopall` — Kill all bots
`.restart <id>` — Restart a bot
`.info` — Server info
`.clear` — Delete this message

━━━━━━━━━━━━━━━━━━━━━
**🎙 VOICE COMMANDS**
━━━━━━━━━━━━━━━━━━━━━
Say **"Jarvis"** then:

📨 **Messaging**
• _"message @username hello there"_
• _"send John hey are you free?"_
• _"msg saved messages test"_

🤖 **Bot Deployment**
• _"deploy a bot that does X"_

📊 **Control**
• _"status"_ — running bots
• _"stop bot <id>"_

━━━━━━━━━━━━━━━━━━━━━
**💡 TIPS**
━━━━━━━━━━━━━━━━━━━━━
• Use @username or contact name for messaging
• "Saved messages" sends to your own Saved
• Session string needed for Render deploy
"""


# ─────────────────────────────────────────────
#  REGISTRY
# ─────────────────────────────────────────────
def registry_load() -> dict:
    if os.path.exists(REGISTRY_FILE):
        try:
            return json.load(open(REGISTRY_FILE))
        except Exception:
            pass
    return {}


def registry_save(data: dict):
    with open(REGISTRY_FILE, "w") as f:
        json.dump(data, f, indent=2)


def registry_add(bot_id: str, name: str, message_id: int, log_path: str):
    data = registry_load()
    data[bot_id] = {
        "name": name, "message_id": message_id,
        "log": log_path, "registered": time.time(),
    }
    registry_save(data)


def registry_remove(bot_id: str):
    data = registry_load()
    data.pop(bot_id, None)
    registry_save(data)


# ─────────────────────────────────────────────
#  AUTO-RECOVERY
# ─────────────────────────────────────────────
async def auto_recover(client: Client):
    registry = registry_load()
    if not registry:
        log.info("Registry empty — clean start.")
        return

    log.info(f"Recovering {len(registry)} bot(s)...")
    notify = await client.send_message(
        LOG_GROUP_ID,
        f"🔄 **Jarvis restarted** — recovering {len(registry)} bot(s)..."
    )
    recovered, failed = 0, []

    for bot_id, meta in registry.items():
        try:
            msg_id   = meta["message_id"]
            name     = meta["name"]
            log_path = meta.get("log", os.path.join(DEPLOY_DIR, f"bot_{bot_id}.log"))
            bot_path = os.path.join(DEPLOY_DIR, f"bot_{bot_id}.py")

            message: Message = await client.get_messages(LOG_GROUP_ID, msg_id)
            if not message or not message.document:
                raise ValueError(f"Message {msg_id} has no document.")

            await client.download_media(message, file_name=bot_path)
            code = open(bot_path).read()
            safe, reason = is_code_safe(code)
            if not safe:
                raise ValueError(f"Safety blocked: {reason}")

            lf = open(log_path, "a")
            lf.write(f"\n\n--- Recovered {datetime.now()} ---\n")
            proc = subprocess.Popen(
                [VENV_PYTHON, bot_path],
                stdout=lf, stderr=subprocess.STDOUT, cwd=DEPLOY_DIR,
            )
            await asyncio.sleep(2)
            if proc.poll() is not None:
                raise RuntimeError("Crashed immediately.")

            running_bots[bot_id] = {
                "proc": proc, "name": name, "started": time.time(),
                "log": log_path, "message_id": msg_id,
            }
            recovered += 1
            log.info(f"  ✅ {bot_id} ({name}) online.")

        except Exception as e:
            log.error(f"  ❌ {bot_id} failed: {e}")
            failed.append(f"`{bot_id}` — {e}")

    lines = [f"✅ **{recovered}/{len(registry)} recovered.**"]
    if failed:
        lines += ["\n❌ **Failed:**"] + failed
    await notify.edit("\n".join(lines))


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
async def run_ollama(prompt: str) -> str:
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None, lambda: ollama.generate(model=MODEL, prompt=prompt)
    )
    return resp["response"]


def is_code_safe(code: str) -> tuple[bool, str]:
    BANNED = [
        r"os\.system\s*\(", r"shutil\.rmtree",
        r"subprocess\.call.*rm\s", r"open\s*\(.*['\"]\/etc",
        r"__import__\s*\(\s*['\"]os['\"]",
        r"exec\s*\(", r"eval\s*\(", r"importlib",
    ]
    for p in BANNED:
        if re.search(p, code):
            return False, f"Blocked: `{p}`"
    return True, "OK"


def clean_code_block(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:python)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


async def send_to_cloud(client, file_path: str, caption: str) -> int:
    msg = await client.send_document(chat_id=LOG_GROUP_ID, document=file_path, caption=caption)
    if os.path.exists(file_path):
        os.remove(file_path)
    return msg.id


def uptime_str(started: float) -> str:
    secs = int(time.time() - started)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


def transcribe_voice(file_path: str) -> str | None:
    wav_path = file_path + ".wav"
    try:
        audio = AudioSegment.from_file(file_path, format="ogg")
        audio.export(wav_path, format="wav")
        with sr.AudioFile(wav_path) as source:
            return recognizer.recognize_google(recognizer.record(source))
    except Exception as e:
        log.warning(f"Transcription failed: {e}")
        return None
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


def get_system_info() -> str:
    try:
        cpu    = subprocess.check_output("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'", shell=True).decode().strip()
        mem    = subprocess.check_output("free -h | awk '/Mem/{print $3\"/\"$2}'", shell=True).decode().strip()
        disk   = subprocess.check_output("df -h / | awk 'NR==2{print $3\"/\"$2}'", shell=True).decode().strip()
        uptime = subprocess.check_output("uptime -p", shell=True).decode().strip()
        return f"🖥 CPU: `{cpu}%` | 💾 RAM: `{mem}` | 💿 Disk: `{disk}` | ⏱ Up: `{uptime}`"
    except Exception:
        return "⚠️ Could not fetch system info."


# ─────────────────────────────────────────────
#  MESSAGING HANDLER
# ─────────────────────────────────────────────
async def handle_send_message(client: Client, status, intent: dict):
    """
    Handles voice intent: send a message to a contact or chat.
    intent = {"action":"message","target":"@username or name","text":"message body"}
    """
    target_raw = intent.get("target", "").strip()
    msg_text   = intent.get("text", "").strip()

    if not target_raw or not msg_text:
        await status.edit("❌ Could not parse target or message text.")
        return

    # Resolve "saved messages" / "me" / "myself"
    if target_raw.lower() in ("saved messages", "me", "myself", "saved"):
        target = "me"
    elif target_raw.startswith("@"):
        target = target_raw          # already a username
    else:
        target = target_raw          # Pyrogram can resolve by name/phone too

    try:
        sent = await client.send_message(target, msg_text)
        chat_name = sent.chat.title or sent.chat.first_name or target
        await status.edit(
            f"📨 **Message sent!**\n"
            f"**To:** {chat_name}\n"
            f"**Text:** `{msg_text}`"
        )
    except Exception as e:
        await status.edit(f"❌ Failed to send message: `{e}`")


# ─────────────────────────────────────────────
#  SHARED HELPERS
# ─────────────────────────────────────────────
async def _status_reply(target):
    if not running_bots:
        text = "📊 No bots running."
    else:
        lines = ["📊 **Running Bots:**\n"]
        for bid, info in running_bots.items():
            alive = info["proc"].poll() is None
            icon  = "🟢" if alive else "🔴"
            lines.append(f"{icon} `{bid}` — {info['name']} — ⏱ {uptime_str(info['started'])}")
        text = "\n".join(lines)
    await (target.edit(text) if hasattr(target, "edit") else target.reply(text))


async def _stop_bot(target, bot_id: str | None):
    if not bot_id and running_bots:
        bot_id = list(running_bots.keys())[-1]
    if bot_id and bot_id in running_bots:
        running_bots[bot_id]["proc"].terminate()
        del running_bots[bot_id]
        registry_remove(bot_id)
        msg = f"🛑 Bot `{bot_id}` stopped & removed from registry."
    else:
        msg = "❓ Bot not found."
    await (target.edit(msg) if hasattr(target, "edit") else target.reply(msg))


async def _restart_bot(target, bot_id: str):
    registry = registry_load()
    if bot_id not in registry:
        txt = "❓ Not in registry."
        await (target.edit(txt) if hasattr(target, "edit") else target.reply(txt))
        return

    if bot_id in running_bots:
        running_bots[bot_id]["proc"].terminate()
        del running_bots[bot_id]

    meta     = registry[bot_id]
    bot_path = os.path.join(DEPLOY_DIR, f"bot_{bot_id}.py")
    log_path = meta.get("log", os.path.join(DEPLOY_DIR, f"bot_{bot_id}.log"))

    txt   = f"🔁 Restarting `{bot_id}`..."
    reply = await (target.edit(txt) if hasattr(target, "edit") else target.reply(txt))

    try:
        if not os.path.exists(bot_path):
            message: Message = await app.get_messages(LOG_GROUP_ID, meta["message_id"])
            await app.download_media(message, file_name=bot_path)

        lf = open(log_path, "a")
        lf.write(f"\n\n--- Restarted {datetime.now()} ---\n")
        proc = subprocess.Popen(
            [VENV_PYTHON, bot_path],
            stdout=lf, stderr=subprocess.STDOUT, cwd=DEPLOY_DIR,
        )
        await asyncio.sleep(2)
        if proc.poll() is not None:
            raise RuntimeError("Crashed on restart.")

        running_bots[bot_id] = {
            "proc": proc, "name": meta["name"], "started": time.time(),
            "log": log_path, "message_id": meta["message_id"],
        }
        result = f"✅ Bot `{bot_id}` restarted."
    except Exception as e:
        result = f"💥 Restart failed: {e}"

    await (reply.edit(result) if hasattr(reply, "edit") else reply.reply(result))


# ─────────────────────────────────────────────
#  TEXT COMMANDS
# ─────────────────────────────────────────────
@app.on_message(filters.me & filters.text & filters.regex(r"^\."))
async def dot_commands(client, message):
    text = message.text.strip()
    cmd  = text.split()[0].lower()
    args = text.split()[1:]

    if cmd == ".help":
        await message.edit(HELP_TEXT)

    elif cmd == ".ping":
        t = time.time()
        m = await message.edit("🏓 Pong!")
        ms = int((time.time() - t) * 1000)
        await m.edit(f"🏓 **Pong!** `{ms}ms`")

    elif cmd == ".status":
        await _status_reply(message)

    elif cmd == ".registry":
        data = registry_load()
        if not data:
            await message.edit("📋 Registry is empty.")
        else:
            lines = ["📋 **Registry:**\n"]
            for bid, meta in data.items():
                ts = datetime.fromtimestamp(meta["registered"]).strftime("%d %b %H:%M")
                lines.append(f"• `{bid}` — {meta['name']} — {ts}")
            await message.edit("\n".join(lines))

    elif cmd == ".log":
        if not args:
            await message.edit("Usage: `.log <bot_id>`")
            return
        bot_id   = args[0]
        info     = running_bots.get(bot_id) or registry_load().get(bot_id)
        log_path = (info or {}).get("log", os.path.join(DEPLOY_DIR, f"bot_{bot_id}.log"))
        if os.path.exists(log_path):
            tail = open(log_path).read()[-2000:]
            await message.edit(f"📋 **Log `{bot_id}`:**\n```\n{tail}\n```")
        else:
            await message.edit("⚠️ Log not found.")

    elif cmd == ".stop":
        await _stop_bot(message, args[0] if args else None)

    elif cmd == ".stopall":
        for info in running_bots.values():
            info["proc"].terminate()
        count = len(running_bots)
        running_bots.clear()
        registry_save({})
        await message.edit(f"🛑 Stopped **{count}** bot(s). Registry cleared.")

    elif cmd == ".restart":
        if not args:
            await message.edit("Usage: `.restart <bot_id>`")
            return
        await _restart_bot(message, args[0])

    elif cmd == ".info":
        bots_alive = len([b for b in running_bots.values() if b["proc"].poll() is None])
        await message.edit(
            f"⚡ **Jarvis Ghost Server**\n\n"
            f"{get_system_info()}\n\n"
            f"🤖 Model: `{MODEL}`\n"
            f"🟢 Bots running: `{bots_alive}`\n"
            f"📋 Registered: `{len(registry_load())}`\n"
            f"📁 Deploy dir: `{DEPLOY_DIR}`"
        )

    elif cmd == ".clear":
        await message.delete()


# ─────────────────────────────────────────────
#  VOICE HANDLER
# ─────────────────────────────────────────────
@app.on_message(filters.me & filters.voice)
async def voice_logic(client, message):
    status = await message.reply("📡 **Intercepting frequencies...**")
    path   = await message.download()
    text   = transcribe_voice(path)
    os.remove(path)

    if not text:
        await status.edit("❌ Could not transcribe.")
        return
    if "jarvis" not in text.lower():
        await status.edit(f"🔇 No trigger.\n`{text}`")
        return

    await status.edit(f"🎙 `{text}`\n\n🧠 Thinking...")

    # Let Gemma parse intent — now includes "message" action
    raw = await run_ollama(
        f"User said: '{text}'.\n"
        "Parse the intent and return ONLY a JSON object.\n\n"
        "If user wants to send a message to someone:\n"
        '{"action":"message","target":"@username or contact name","text":"the message to send"}\n\n'
        "If user wants to deploy a bot:\n"
        '{"action":"deploy","desc":"what the bot does","token":"bot token or null"}\n\n'
        "If user wants status:\n"
        '{"action":"status"}\n\n'
        "If user wants to stop a bot:\n"
        '{"action":"stop","bot_id":"id or null"}\n\n'
        "Anything else:\n"
        '{"action":"unknown","message":"short reply"}\n\n'
        "Return ONLY the JSON. No explanation."
    )

    try:
        intent = json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group())
    except Exception:
        await status.edit(f"🤖 {raw}")
        return

    action = intent.get("action", "unknown")

    if action == "message":
        await handle_send_message(client, status, intent)

    elif action == "status":
        await _status_reply(status)

    elif action == "stop":
        await _stop_bot(status, intent.get("bot_id"))

    elif action == "unknown":
        await status.edit(f"🤖 **Jarvis:** {intent.get('message', raw)}")

    elif action == "deploy":
        pending_orders[message.from_user.id] = {
            "text": text, "desc": intent.get("desc", text), "token": intent.get("token"),
        }
        kb = types.InlineKeyboardMarkup([[
            types.InlineKeyboardButton("🚀 Deploy",  callback_data="confirm_deploy"),
            types.InlineKeyboardButton("❌ Cancel",  callback_data="cancel_deploy"),
        ]])
        await status.edit(
            f"🎙 `{text}`\n\n"
            f"🤖 **Plan:** {intent.get('desc')}\n"
            f"🔑 Token: `{'provided' if intent.get('token') else 'not detected'}`\n\nDeploy?",
            reply_markup=kb,
        )


# ─────────────────────────────────────────────
#  DEPLOY FLOW
# ─────────────────────────────────────────────
@app.on_callback_query(filters.regex("confirm_deploy"))
async def deploy_logic(client, callback_query):
    user_id = callback_query.from_user.id
    order   = pending_orders.pop(user_id, None)
    if not order:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.message.edit("🏗 Generating code with Gemma...")
    token_hint = (
        f"Use this bot token: {order['token']}."
        if order["token"] else
        "Use os.getenv('BOT_TOKEN') for the token."
    )
    raw_code = await run_ollama(
        f"Write a complete Telegram bot (python-telegram-bot v20+, async).\n"
        f"Purpose: {order['desc']}\n{token_hint}\n"
        "Use ApplicationBuilder + run_polling(). Add /start. Only output Python code."
    )
    code = clean_code_block(raw_code)

    safe, reason = is_code_safe(code)
    if not safe:
        await callback_query.message.edit(f"🚫 Safety check failed: {reason}")
        return

    bot_id   = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:8]
    bot_path = os.path.join(DEPLOY_DIR, f"bot_{bot_id}.py")
    log_path = os.path.join(DEPLOY_DIR, f"bot_{bot_id}.log")

    with open(bot_path, "w") as f:
        f.write(code)

    await callback_query.message.edit("🔍 Safety OK — Launching...")
    lf   = open(log_path, "w")
    proc = subprocess.Popen(
        [VENV_PYTHON, bot_path], stdout=lf,
        stderr=subprocess.STDOUT, cwd=DEPLOY_DIR,
    )
    await asyncio.sleep(3)
    if proc.poll() is not None:
        crash = open(log_path).read()[-1000:] if os.path.exists(log_path) else "No log."
        await callback_query.message.edit(f"💥 Crashed!\n```\n{crash}\n```")
        await send_to_cloud(client, bot_path, f"❌ Crashed | {bot_id}")
        return

    msg_id = await send_to_cloud(
        client, bot_path,
        f"✅ Bot `{bot_id}` | {order['desc'][:60]}"
    )
    running_bots[bot_id] = {
        "proc": proc, "name": order["desc"][:40],
        "started": time.time(), "log": log_path, "message_id": msg_id,
    }
    registry_add(bot_id, order["desc"][:40], msg_id, log_path)

    await callback_query.message.edit(
        f"🚀 **Bot `{bot_id}` Online!**\n"
        f"📝 {order['desc']}\n"
        f"💾 Auto-recovery enabled.\n"
        f"📁 Source in log group (msg `{msg_id}`).\n\n"
        f"Use `.log {bot_id}` to view output."
    )


@app.on_callback_query(filters.regex("cancel_deploy"))
async def cancel_deploy(client, callback_query):
    pending_orders.pop(callback_query.from_user.id, None)
    await callback_query.message.edit("❌ Cancelled.")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
async def main():
    async with app:
        log.info("⚡ Jarvis Ghost Server Online...")
        await auto_recover(app)
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
    
