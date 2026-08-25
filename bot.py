import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from dotenv import load_dotenv
from eval_bridge import register_bot, app as eval_app
from flask import Flask
from threading import Thread
import asyncio
import sys
import logging
import uvicorn
import certifi
import aiohttp
import random
from redis_utils import rget_json

# --- 1. GLOBAL SSL FIX ---
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['SSL_CERT_DIR'] = os.path.dirname(certifi.where())

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.info("⌬ ⟡ **𝒮𝒯ℰℒℒ𝒜ℛ 𝒞𝒪ℛℰ: 𝒱𝒜𝒩𝒢𝒰𝒜ℛ𝒟 ℰ𝒩𝒢ℐ𝒩ℰ v3.1**")

# --- 2. THE DOH MASTER BYPASS (DNS OVER HTTPS) ---
async def fetch_discord_ips():
    """Fetches real terminal IPs via Google's DNS-over-HTTPS API."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://dns.google/resolve?name=discord.com&type=A", timeout=2.0) as r1:
                d_com = await r1.json()
            async with session.get("https://dns.google/resolve?name=gateway.discord.gg&type=A", timeout=2.0) as r2:
                d_gg = await r2.json()
            
            com_ips = [ans['data'] for ans in d_com.get('Answer', []) if ans['type'] == 1]
            gg_ips = [ans['data'] for ans in d_gg.get('Answer', []) if ans['type'] == 1]
            return com_ips, gg_ips
        except Exception:
            return [], []

import socket
DISCORD_COM_IPS, DISCORD_GG_IPS = [], []
original_getaddrinfo = socket.getaddrinfo

def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    safe_host = host.decode('utf-8') if isinstance(host, bytes) else host
    if safe_host == "discord.com" and DISCORD_COM_IPS:
        return original_getaddrinfo(random.choice(DISCORD_COM_IPS), port, family, type, proto, flags)
    elif safe_host == "gateway.discord.gg" and DISCORD_GG_IPS:
        return original_getaddrinfo(random.choice(DISCORD_GG_IPS), port, family, type, proto, flags)
    return original_getaddrinfo(host, port, family, type, proto, flags)

if os.environ.get("SPACE_ID") or os.environ.get("SPACE_HOST"):
    socket.getaddrinfo = patched_getaddrinfo

# --- 3. WEB SERVER SETUP ---
app = Flask(__name__)
@app.route("/", methods=["GET", "POST"])
def home(): return "Hyacine is alive and guarding Hugging Face."

def keep_alive():
    if not (os.environ.get("SPACE_ID") or os.environ.get("SPACE_HOST") or os.environ.get("PORT")):
        return
    try:
        port = int(os.environ.get("PORT", 7860))
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        logging.info(f"⌬ ⟡ Initiating Keep-Alive Heartbeat on port {port}...")
        Thread(target=lambda: app.run(host="0.0.0.0", port=port, use_reloader=False), daemon=True).start()
    except Exception as e:
        logging.info(f"Keep-alive webserver notice: {e}")

# --- 4. BOT CONFIGURATION ---
load_dotenv()

HYACINE_DEFAULT_PREFIXES = ["!", ",", "hya ", "hya"]

async def get_server_prefixes(bot, message):
    default_p = ["hya ", "hya", "!", ","]
    if not message.guild:
        return commands.when_mentioned_or(*default_p)(bot, message)
    try:
        prefixes = await rget_json(bot, f"prefixes:{message.guild.id}")
        if isinstance(prefixes, list) and prefixes:
            expanded = []
            for p in prefixes + default_p:
                if not p.endswith(" ") and p.isalnum():
                    if (p + " ") not in expanded:
                        expanded.append(p + " ")
                if p not in expanded:
                    expanded.append(p)
            return commands.when_mentioned_or(*expanded)(bot, message)
    except: pass
    return commands.when_mentioned_or(*default_p)(bot, message)

class HyacineBot(commands.Bot):
    def __init__(self, proxy_url=None):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        super().__init__(
            command_prefix=get_server_prefixes,
            intents=intents,
            proxy=proxy_url,
            help_command=None
        )
        self._tree_synced = False

    async def setup_hook(self):
        register_bot(self)

        extensions = [
            "cogs.staff_cmds", "cogs.impersonator", "cogs.fun_cmds",
            "cogs.admin_cmds", "cogs.sticky_cmds", "cogs.forcenick_cmds",
            "cogs.afk_cmds", "cogs.help_cmds", "cogs.mysterymail_cmds",
            "cogs.confession_cmds", "cogs.infrastructure_engine",
            "cogs.observability_engine", "cogs.autodelete_engine"
        ]
        for ext in extensions:
            try: await self.load_extension(ext)
            except Exception as e: logging.error(f"Failed {ext}: {e}")

    async def on_ready(self):
        logging.info(f"SUCCESS: {self.user} is online via Autonomous Relay.")
        if not self._tree_synced:
            try:
                synced = await self.tree.sync()
                logging.info(f"Successfully synced {len(synced)} global app commands.")
                self._tree_synced = True
            except Exception as e:
                logging.error(f"Global app command sync notice: {e}")

# --- 5. STARTUP ---
async def main():
    load_dotenv()
    token = os.getenv("dc_token") or os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")

    keep_alive()
    if not token:
        logging.error("❌ CRITICAL: No Discord Bot Token found! Please set Secret 'dc_token' or 'DISCORD_TOKEN' in .env")
        return

    bot = HyacineBot()
    try:
        async with bot:
            await bot.start(token)
    except Exception as e:
        logging.error(f"Link Failure: {e}")

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
