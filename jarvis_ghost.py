import os, asyncio, logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Required Env Vars ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
GROK_API_KEY = os.getenv("GROK_API_KEY")

# --- Optional Env Vars with defaults ---
OWNER_ID = int(os.getenv("OWNER_ID", "1214273889"))
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "0"))
MODEL = os.getenv("MODEL", "grok-2-latest")
DEPLOY_DIR = os.getenv("DEPLOY_DIR", "downloads")
REGISTRY_FILE = os.getenv("REGISTRY_FILE", "registry.json")
AUTO_REPLY = os.getenv("AUTO_REPLY", "false").lower() == "true"

grok = AsyncOpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# --- Helper ---
async def log_to_group(text):
    try:
        if LOG_GROUP_ID!= 0:
            await client.send_message(LOG_GROUP_ID, f"**LOG:**\n{text}")
    except: pass

async def ask_ai(prompt, system="You are a helpful assistant."):
    try:
        response = await grok.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ]
        )
        await asyncio.sleep(3) # Grok rate limit safety
        return response.choices[0].message.content
    except Exception as e:
        await log_to_group(f"Grok Error: {str(e)}")
        return f"Grok Error: {str(e)}"

def is_owner(event):
    return event.sender_id == OWNER_ID

# --- Commands ---
@client.on(events.NewMessage(outgoing=True, pattern=r'\.ai (.+)'))
async def ai_cmd(event):
    if not is_owner(event): return
    msg = await event.edit("`Thinking...`")
    await msg.edit(await ask_ai(event.pattern_match.group(1)))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.ask (.+)'))
async def ask_reply(event):
    if not is_owner(event): return
    reply_msg = await event.get_reply_message()
    if not reply_msg: return await event.edit("Reply to a message")
    msg = await event.edit("`Thinking...`")
    prompt = f"Context: {reply_msg.text}\n\nQuestion: {event.pattern_match.group(1)}"
    await msg.edit(await ask_ai(prompt))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.summarize (\d+)'))
async def summarize(event):
    if not is_owner(event): return
    limit = min(int(event.pattern_match.group(1)), 100)
    msg = await event.edit(f"`Summarizing {limit} msgs...`")
    msgs = await client.get_messages(event.chat_id, limit=limit)
    text = "\n".join([f"{m.sender.first_name if m.sender else 'User'}: {m.text}" for m in msgs if m.text])
    await msg.edit(await ask_ai(f"Summarize in bullet points:\n{text}"))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.tldr'))
async def tldr(event):
    if not is_owner(event): return
    reply_msg = await event.get_reply_message()
    if not reply_msg: return await event.edit("Reply to a message")
    msg = await event.edit("`TLDR...`")
    await msg.edit(await ask_ai(f"TLDR in 1-2 sentences: {reply_msg.text}"))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.tr (\w{2})'))
async def translate(event):
    if not is_owner(event): return
    reply_msg = await event.get_reply_message()
    if not reply_msg: return await event.edit("Reply to text")
    lang = event.pattern_match.group(1)
    msg = await event.edit("`Translating...`")
    await msg.edit(await ask_ai(f"Translate to {lang}. Only return translation: {reply_msg.text}"))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.fix'))
async def grammar(event):
    if not is_owner(event): return
    reply_msg = await event.get_reply_message()
    if not reply_msg: return await event.edit("Reply to text")
    msg = await event.edit("`Fixing...`")
    await msg.edit(await ask_ai(f"Fix grammar and improve clarity. Return only corrected text: {reply_msg.text}"))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.tone (\w+)'))
async def tone(event):
    if not is_owner(event): return
    reply_msg = await event.get_reply_message()
    if not reply_msg: return await event.edit("Reply to text")
    tone = event.pattern_match.group(1)
    msg = await event.edit(f"`Changing to {tone}...`")
    await msg.edit(await ask_ai(f"Rewrite in {tone} tone: {reply_msg.text}"))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.code (.+)'))
async def code(event):
    if not is_owner(event): return
    msg = await event.edit("`Coding...`")
    await msg.edit(await ask_ai(f"Write Python code for: {event.pattern_match.group(1)}. Use markdown block.", "You are a coding assistant."))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.explain'))
async def explain_code(event):
    if not is_owner(event): return
    reply_msg = await event.get_reply_message()
    if not reply_msg: return await event.edit("Reply to code")
    msg = await event.edit("`Explaining...`")
    await msg.edit(await ask_ai(f"Explain this code simply:\n{reply_msg.text}", "You are a coding tutor."))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.debug'))
async def debug(event):
    if not is_owner(event): return
    reply_msg = await event.get_reply_message()
    if not reply_msg: return await event.edit("Reply to code")
    msg = await event.edit("`Debugging...`")
    await msg.edit(await ask_ai(f"Find bugs and fix. Explain what was wrong:\n{reply_msg.text}", "You are a debugging expert."))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.vision (.+)'))
async def vision(event):
    if not is_owner(event): return
    await event.edit("`Grok API doesn't support vision yet. Use.ai to describe images manually.`")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.ocr'))
async def ocr(event):
    if not is_owner(event): return
    await event.edit("`Grok API doesn't support OCR yet.`")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.roast'))
async def roast(event):
    if not is_owner(event): return
    reply_msg = await event.get_reply_message()
    if not reply_msg: return await event.edit("Reply to someone")
    sender = await reply_msg.get_sender()
    name = sender.first_name if isinstance(sender, User) else "User"
    msg = await event.edit("`Cooking...`")
    await msg.edit(await ask_ai(f"Playful roast for {name} in 1-2 sentences: {reply_msg.text}", "You are witty and playful."))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.meme'))
async def meme(event):
    if not is_owner(event): return
    reply_msg = await event.get_reply_message()
    text = reply_msg.text if reply_msg else "make a meme"
    msg = await event.edit("`Memeing...`")
    await msg.edit(await ask_ai(f"Turn this into a funny meme caption: {text}", "You are a meme creator."))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.ping'))
async def ping(event):
    if not is_owner(event): return
    await event.edit(f"`Pong! Owner: {OWNER_ID} | Model: {MODEL}`")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.id'))
async def get_id(event):
    if not is_owner(event): return
    reply_msg = await event.get_reply_message()
    if reply_msg:
        sender = await reply_msg.get_sender()
        await event.edit(f"**User:** `{sender.id}`\n**Chat:** `{event.chat_id}`")
    else:
        await event.edit(f"**Chat:** `{event.chat_id}`\n**You:** `{OWNER_ID}`")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.dl'))
async def download(event):
    if not is_owner(event): return
    reply_msg = await event.get_reply_message()
    if not reply_msg or not reply_msg.media: return await event.edit("Reply to media")
    msg = await event.edit("`Downloading...`")
    path = await reply_msg.download_media(file=f"{DEPLOY_DIR}/")
    await msg.edit(f"**Downloaded:** `{path}`")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.help'))
async def help_cmd(event):
    if not is_owner(event): return
    await event.edit("""
**Grok AI Commands**
`.ai <q>` | `.ask <q>` - reply | `.summarize <n>` | `.tldr` - reply
`.tr <lang>` | `.fix` | `.tone <type>` - reply
`.code <task>` | `.explain` | `.debug` - reply to code
`.roast` | `.meme` - reply
`.ping` | `.id` | `.dl` - reply to media
`.vision` | `.ocr` - disabled, no vision API yet
""")

# --- Auto Reply ---
@client.on(events.NewMessage(incoming=True))
async def auto_reply_dm(event):
    if event.is_private and not event.out and is_owner(event) and AUTO_REPLY:
        await asyncio.sleep(2)
        sender = await event.get_sender()
        reply = await ask_ai(f"You are me. Reply casually to {sender.first_name}: {event.text}")
        await event.reply(reply)

# --- Start ---
async def main():
    await client.start()
    await log_to_group(f"Userbot started. Owner: {OWNER_ID} | Model: {MODEL}")
    logging.info(f"Started. Owner: {OWNER_ID}")
    await client.run_until_disconnected()

if __name__ == '__main__':
    os.makedirs(DEPLOY_DIR, exist_ok=True)
    asyncio.run(main())
