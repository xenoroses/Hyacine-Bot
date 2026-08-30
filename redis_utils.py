import json
import os
import asyncio
import logging
import aiohttp
from typing import Optional, Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STORE_FILE = os.path.join(DATA_DIR, "hyacine_store.json")

# Default Upstash credentials if not explicitly set in environment
DEFAULT_UPSTASH_URL = "https://great-camel-72413.upstash.io"
DEFAULT_UPSTASH_TOKEN = "gQAAAAAAARrdAAIgcDJhNGMyOWYzMmY5MjQ0YmYxYjI2NWI1N2NhZWNiNmZjZQ"

UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", DEFAULT_UPSTASH_URL).rstrip("/")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", DEFAULT_UPSTASH_TOKEN).strip()

_MEMORY_STORE = {}
_AIOHTTP_SESSION: Optional[aiohttp.ClientSession] = None

def _get_headers():
    return {"Authorization": f"Bearer {UPSTASH_TOKEN}"}

async def _get_session() -> aiohttp.ClientSession:
    global _AIOHTTP_SESSION
    if _AIOHTTP_SESSION is None or _AIOHTTP_SESSION.closed:
        _AIOHTTP_SESSION = aiohttp.ClientSession(headers=_get_headers(), timeout=aiohttp.ClientTimeout(total=3.0))
    return _AIOHTTP_SESSION

def _load_store_from_disk():
    global _MEMORY_STORE
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(STORE_FILE):
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                _MEMORY_STORE = json.load(f)
                logging.info(f"Loaded {len(_MEMORY_STORE)} keys from local disk store.")
    except Exception as e:
        logging.error(f"Failed loading hyacine_store.json: {e}")
        _MEMORY_STORE = {}

def _save_store_to_disk():
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        with open(STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(_MEMORY_STORE, f, indent=2)
    except Exception as e:
        logging.error(f"Failed saving hyacine_store.json to disk: {e}")

# Load store immediately on module import
_load_store_from_disk()

async def upstash_get(key: str) -> Optional[str]:
    """Fetch value directly from Upstash Cloud Redis REST API with graceful error handling."""
    if not UPSTASH_URL or not UPSTASH_TOKEN:
        return None
    try:
        session = await _get_session()
        async with session.get(f"{UPSTASH_URL}/get/{key}") as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("result")
    except Exception:
        pass
    return None

async def upstash_set(key: str, value: str) -> bool:
    """Store value directly in Upstash Cloud Redis REST API with quota resilience."""
    if not UPSTASH_URL or not UPSTASH_TOKEN:
        return False
    try:
        session = await _get_session()
        async with session.post(f"{UPSTASH_URL}/set/{key}", data=value) as resp:
            return resp.status == 200
    except Exception:
        pass
    return False

async def upstash_del(key: str) -> bool:
    """Delete key directly from Upstash Cloud Redis REST API."""
    if not UPSTASH_URL or not UPSTASH_TOKEN:
        return False
    try:
        session = await _get_session()
        async with session.post(f"{UPSTASH_URL}/del/{key}") as resp:
            return resp.status == 200
    except Exception:
        pass
    return False

# --- Public API Wrappers (Zero-Downtime Memory + Cloud Hybrid) ---

async def rget(bot, key: str, default=None):
    """Fast RAM read with Upstash Cloud Redis sync and disk fallback."""
    skey = str(key)
    if skey in _MEMORY_STORE and _MEMORY_STORE[skey] is not None:
        val = _MEMORY_STORE[skey]
        if isinstance(val, (dict, list)): return json.dumps(val)
        return str(val)

    up_val = await upstash_get(skey)
    if up_val is not None:
        _MEMORY_STORE[skey] = up_val
        _save_store_to_disk()
        return up_val

    val = _MEMORY_STORE.get(skey, default)
    if val is None: return default
    if isinstance(val, (dict, list)): return json.dumps(val)
    return str(val)

async def rset(bot, key: str, value: Any):
    """Set value in RAM, local disk, and Upstash Cloud Redis asynchronously."""
    skey = str(key)
    val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
    _MEMORY_STORE[skey] = value
    _save_store_to_disk()
    asyncio.create_task(upstash_set(skey, val_str))

async def rget_json(bot, key: str):
    """Fast RAM JSON read with Upstash Cloud Redis sync and disk fallback."""
    skey = str(key)
    if skey in _MEMORY_STORE and _MEMORY_STORE[skey] is not None:
        data = _MEMORY_STORE[skey]
        if isinstance(data, (dict, list)): return data
        try:
            parsed = json.loads(data)
            if isinstance(parsed, str):
                try: parsed = json.loads(parsed)
                except: pass
            return parsed
        except: pass

    up_val = await upstash_get(skey)
    if up_val is not None:
        try:
            parsed = json.loads(up_val)
            if isinstance(parsed, str):
                try: parsed = json.loads(parsed)
                except: pass
            _MEMORY_STORE[skey] = parsed
            _save_store_to_disk()
            return parsed
        except Exception:
            pass

    data = _MEMORY_STORE.get(skey)
    if data is None: return None
    if isinstance(data, (dict, list)): return data
    try:
        parsed = json.loads(data)
        if isinstance(parsed, str):
            try: parsed = json.loads(parsed)
            except: pass
        return parsed
    except Exception:
        return None

async def rset_json(bot, key: str, value: Any):
    """Store JSON in RAM, local disk, and Upstash Cloud Redis asynchronously."""
    skey = str(key)
    if isinstance(value, (dict, list)):
        _MEMORY_STORE[skey] = value
        val_str = json.dumps(value)
    else:
        try:
            _MEMORY_STORE[skey] = json.loads(value)
            val_str = value
        except Exception:
            _MEMORY_STORE[skey] = value
            val_str = str(value)
    _save_store_to_disk()
    asyncio.create_task(upstash_set(skey, val_str))

async def rappend(bot, key: str, value: str):
    """Append a value to a list in RAM, local disk, and Upstash Cloud Redis."""
    skey = str(key)
    current = await rget_json(bot, skey) or []
    if not isinstance(current, list): current = [current]
    current.append(value)
    await rset_json(bot, skey, current)

async def rrange(bot, key: str, start: int = 0, stop: int = -1):
    """Fetch list range from RAM or Upstash Cloud Redis."""
    skey = str(key)
    current = await rget_json(bot, skey) or []
    if not isinstance(current, list): return []
    if stop == -1: return [str(x) for x in current[start:]]
    return [str(x) for x in current[start:stop+1]]

async def rdelete(bot, key: str):
    """Delete key from RAM, local disk, and Upstash Cloud Redis asynchronously."""
    skey = str(key)
    _MEMORY_STORE.pop(skey, None)
    _save_store_to_disk()
    asyncio.create_task(upstash_del(skey))
