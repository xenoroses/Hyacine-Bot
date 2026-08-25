import json
import os
import asyncio
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STORE_FILE = os.path.join(DATA_DIR, "hyacine_store.json")

_MEMORY_STORE = {}

def _load_store_from_disk():
    global _MEMORY_STORE
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(STORE_FILE):
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                _MEMORY_STORE = json.load(f)
                logging.info(f"Loaded {len(_MEMORY_STORE)} keys from persistent disk store.")
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

async def rget(bot, key: str, default=None):
    """Fetch value from persistent store."""
    skey = str(key)
    val = _MEMORY_STORE.get(skey, default)
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return str(val)

async def rset(bot, key, value):
    """Set value in persistent store and save to disk."""
    skey = str(key)
    _MEMORY_STORE[skey] = value
    _save_store_to_disk()

async def rget_json(bot, key: str):
    """Fetch and parse JSON safely from persistent store."""
    skey = str(key)
    data = _MEMORY_STORE.get(skey)
    if data is None:
        return None
    if isinstance(data, (dict, list)):
        return data
    try:
        parsed = json.loads(data)
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except Exception:
                pass
        return parsed
    except Exception:
        return None

async def rset_json(bot, key: str, value):
    """Store JSON value in persistent store and save to disk."""
    skey = str(key)
    if isinstance(value, (dict, list)):
        _MEMORY_STORE[skey] = value
    else:
        try:
            _MEMORY_STORE[skey] = json.loads(value)
        except Exception:
            _MEMORY_STORE[skey] = value
    _save_store_to_disk()

async def rappend(bot, key: str, value: str):
    """Append a value to a list in persistent store and save to disk."""
    skey = str(key)
    current = _MEMORY_STORE.get(skey)
    if current is None:
        lst = []
    elif isinstance(current, list):
        lst = current
    else:
        try:
            lst = json.loads(current) if isinstance(current, str) else current
            if not isinstance(lst, list): lst = [current]
        except Exception:
            lst = [current]
    lst.append(value)
    _MEMORY_STORE[skey] = lst
    _save_store_to_disk()

async def rrange(bot, key: str, start: int = 0, stop: int = -1):
    """Fetch range from a list in persistent store."""
    skey = str(key)
    current = _MEMORY_STORE.get(skey)
    if not current:
        return []
    lst = current if isinstance(current, list) else []
    if not lst and isinstance(current, str):
        try:
            lst = json.loads(current)
        except Exception:
            lst = []
    if isinstance(lst, list):
        if stop == -1:
            return [str(x) for x in lst[start:]]
        return [str(x) for x in lst[start:stop+1]]
    return []

async def rdelete(bot, key: str):
    """Delete key from persistent store and update disk."""
    skey = str(key)
    _MEMORY_STORE.pop(skey, None)
    _save_store_to_disk()
