#!/usr/bin/env python3
import aiohttp
from aiohttp_socks import ProxyConnector
import asyncio
import re
from bs4 import BeautifulSoup
import json
import os
from colorama import Fore, Style, init as colorama_init
from email_validator import validate_email, EmailNotValidError
import csv
from datetime import datetime
import hashlib
import aiosqlite
from rich.table import Table
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.panel import Panel
from rich import box
import imagehash
from PIL import Image
from io import BytesIO
import random
from rapidfuzz import fuzz
import langdetect  # pip install langdetect
import time
import sys

colorama_init(autoreset=True)
console = Console()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'shadowtrace.sqlite3')
CONFIG_FILE = os.path.join(BASE_DIR, 'shadowtrace_config.json')
DEFAULT_CONFIG = {
    "timeout": 10,
    "threads": 6,
    "stealth": True,
    "tor": False,
    "proxy_list": [],
    "mode": "passive",  # or 'aggressive'
    "max_retries": 2,
    "sem_delay_ms": [300, 2000],  # min/max Jitter ms
    "passive_ttl_hours": 24,
    "passive_rate_limit_sec": 5,  # Bing etc
}
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
]
ACCEPT_HEADERS = [
    "text/html,application/xhtml+xml,application/xml;q=0.9",
    "application/json;q=0.9,*/*;q=0.8",
]
SEC_CH_UA_HEADERS = [
    '"Chromium";v="121", "Not:A-Brand";v="8"',
    '"Google Chrome";v="120", "Chromium";v="120", "Not:A-Brand";v="24"',
]
REFERERS = [
    "https://www.google.com/", "https://duckduckgo.com/", "https://bing.com/"
]

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            conf = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in conf:
                    conf[k] = v
            return conf
    else:
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG

CONFIG = load_config()

# Upgrade SQLite to WAL & global DB connection for cache/rate
class GlobalDB:
    conn: aiosqlite.Connection = None

    @classmethod
    async def get(cls):
        if not cls.conn:
            cls.conn = await aiosqlite.connect(DB_FILE)
            await cls.conn.execute("PRAGMA journal_mode=WAL;")
            await cls.conn.execute("PRAGMA synchronous=NORMAL;")
        return cls.conn

    @classmethod
    async def close(cls):
        if cls.conn:
            await cls.conn.close()
            cls.conn = None

async def db_init():
    conn = await GlobalDB.get()
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY,
        username TEXT,
        site TEXT,
        url TEXT,
        found INTEGER,
        confidence INTEGER,
        avatar_hash TEXT,
        metadata TEXT,
        last_check TIMESTAMP,
        UNIQUE(username, site)
    )
    """)
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS avatar_hash (
        url TEXT PRIMARY KEY,
        hash TEXT,
        checked_at TIMESTAMP
    )
    """)
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS timeline (
        username TEXT, site TEXT, timestamp TEXT, avatar_hash TEXT, bio TEXT,
        name TEXT, uniqid TEXT, PRIMARY KEY(username, site, timestamp)
    )
    """)
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS passive_cache (
        engine TEXT,
        query TEXT,
        username TEXT,
        snippets TEXT,
        score INTEGER,
        ts TIMESTAMP,
        PRIMARY KEY(engine, query, username)
    )
    """)
    await conn.commit()
asyncio.get_event_loop().run_until_complete(db_init())

# -- SESSION POOL: NUNCA async with session: (bug crítico corrigido!)
class HTTPSessionPool:
    session: aiohttp.ClientSession = None
    semaphore: asyncio.Semaphore = None

    @classmethod
    async def get(cls):
        if cls.session: return cls.session
        timeout = aiohttp.ClientTimeout(total=CONFIG["timeout"])
        proxy = get_proxy()
        connector = None
        if proxy and proxy.startswith("socks"):
            connector = ProxyConnector.from_url(proxy)
        elif proxy:
            connector = aiohttp.TCPConnector()
        sessionkw = dict(timeout=timeout, max_line_size=32768, max_field_size=32768)
        if connector:
            sessionkw['connector'] = connector
        cls.session = aiohttp.ClientSession(**sessionkw)
        return cls.session

    @classmethod
    async def close(cls):
        if cls.session is not None:
            await cls.session.close()
            cls.session = None

    @classmethod
    def get_sem(cls):
        if cls.semaphore is None:
            cls.semaphore = asyncio.Semaphore(CONFIG["threads"])
        return cls.semaphore

def random_stealth_headers():
    # Headers mais realistas p/ stealth
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": random.choice(ACCEPT_HEADERS),
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": random.choice(REFERERS),
        "Sec-CH-UA": random.choice(SEC_CH_UA_HEADERS),
        "DNT": str(random.choice([0, 1])),
        "Upgrade-Insecure-Requests": "1"
    }

def hash_avatar(image_bytes):
    try:
        img = Image.open(BytesIO(image_bytes))
        perceptual = imagehash.phash(img)
        md5 = hashlib.md5(image_bytes).hexdigest()
        return str(perceptual), md5
    except Exception:
        return None, None

def entropic_score(username):
    """Simple heuristic: high entropy = menos humano"""
    return min(100, int(10 * len(set(username)) / max(1, len(username))))

def smart_username_variants(username):
    variants = set([
        username,
        username + '123',
        username + '_',
        '_' + username,
        username.replace('a', '4').replace('o', '0'),
        username + '.dev',
        username + "1",
        username.lower(),
        username.upper(),
        f"real{username}",
        f"the{username}",
        username[::-1],
        re.sub(r'[aeio]', 'x', username),
        username.replace('e', '3'),
    ])
    for year in ["98", "99", "2000", "2020"]:
        variants.add(username + year)
    return list(variants)[:12]

def detect_lang(text):
    try:
        d = langdetect.detect(text)
        return d
    except Exception:
        return "unknown"

# ---- CHALLENGE PAGE DETECTION GENERIC
def detect_challenge(text: str) -> bool:
    text = text.lower()
    triggers = [
        "unusual traffic", "detected unusual traffic", "captcha", "attention required",
        "cloudflare", "access denied", "unusual requests",
        "to continue, please", "please verify you are a human"
    ]
    for t in triggers:
        if t in text:
            return True
    return False

# Passive Cache System (SQLite global for now)
async def passive_cache_get(engine, query, username):
    conn = await GlobalDB.get()
    async with conn.execute(
        "SELECT snippets, score, ts FROM passive_cache WHERE engine=? AND query=? AND username=?",
        (engine, query, username)
    ) as cr:
        row = await cr.fetchone()
        if row:
            snippets, score, ts = row
            # TTL
            dt = datetime.now()
            cache_dt = datetime.fromisoformat(ts)
            if (dt - cache_dt).total_seconds() < CONFIG.get("passive_ttl_hours", 24) * 3600:
                return {
                    "snippets": json.loads(snippets),
                    "score": score,
                    "ts": ts
                }
    return None

async def passive_cache_set(engine, query, username, snippets, score):
    conn = await GlobalDB.get()
    await conn.execute(
        "INSERT OR REPLACE INTO passive_cache (engine, query, username, snippets, score, ts) VALUES (?, ?, ?, ?, ?, ?)",
        (engine, query, username, json.dumps(snippets), score, datetime.now().isoformat())
    )
    await conn.commit()

# -- Advanced correlation (bio/name fuzzy)
def correlation_score(profile_list):
    """Versão avançada com fuzzy, hash, bio/lang, nome e agora rastros passivos"""
    if not profile_list or len(profile_list) < 2:
        return 0
    hashes = {}
    scores = 0
    names = set()
    bios = []
    for prof in profile_list:
        avh = prof.get('avatar_hash')
        if avh:
            if avh in hashes:
                scores += 45
            hashes[avh] = 1
        meta = prof.get('metadata', {})
        bio = meta.get("bio")
        if bio:
            bios.append(bio)
        name = meta.get("full_name") or meta.get("name")
        if name:
            names.add(name.lower())
        # Passivo: Enriching scoring with passive traces!
        if meta.get("passive_score"):
            scores += int(meta["passive_score"]) // 10
    # Fuzzy para bios
    seen_pairs = set()
    if len(set(bios)) == 1 and bios:
        scores += 25
    elif len(bios) > 1:
        fuzzys = []
        for i in range(len(bios)):
            for j in range(i + 1, len(bios)):
                if (i, j) in seen_pairs or (j, i) in seen_pairs:
                    continue
                f = fuzz.ratio(bios[i].lower(), bios[j].lower())
                if f > 60:
                    fuzzys.append(f)
                seen_pairs.add((i, j))
        if fuzzys and max(fuzzys) > 60:
            scores += 15
    if len(names) == 1 and names:
        scores += 20
    return min(99, scores)

def extract_avatar_url(metadata):
    for key in ['avatar_url', "og_image", "profile_pic"]:
        val = metadata.get(key)
        if val:
            return val
    return None

# ------------- CACHE LAYER OTIMIZADA (usando GlobalDB)
async def cache_get(username, site):
    conn = await GlobalDB.get()
    async with conn.execute(
        "SELECT url, found, confidence, avatar_hash, metadata, last_check FROM profiles WHERE username=? AND site=?",
        (username, site)
    ) as cr:
        row = await cr.fetchone()
        if row:
            url, found, confidence, avh, meta, last_check = row
            return {
                "site": site, "url": url, "status": "FOUND" if found else "NOT FOUND",
                "confidence": confidence, "avatar_hash": avh,
                "metadata": json.loads(meta), "cached": True, "last_check": last_check
            }
    return None

async def cache_set(username, site, url, found, confidence, avatar_hash, metadata):
    conn = await GlobalDB.get()
    await conn.execute(
        "INSERT OR REPLACE INTO profiles (username, site, url, found, confidence, avatar_hash, metadata, last_check) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            username, site, url, 1 if found else 0, confidence, avatar_hash,
            json.dumps(metadata), datetime.now().isoformat()
        )
    )
    await conn.commit()
    # timeline update
    await conn.execute(
        "INSERT OR REPLACE INTO timeline (username, site, timestamp, avatar_hash, bio, name, uniqid) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            username, site, datetime.now().isoformat(), avatar_hash,
            metadata.get("bio"), metadata.get("full_name") or "", hashlib.sha1((username+site).encode()).hexdigest()
        )
    )
    await conn.commit()

def get_proxy():
    if CONFIG["tor"]:
        return "socks5://127.0.0.1:9050"
    if CONFIG["proxy_list"]:
        return random.choice(CONFIG["proxy_list"])
    return None

# --------- EXTRACTOR framework v2: fingerprints melhorados
class BaseExtractor:
    SITE_NAME = None
    URL_PATTERNS = []
    @classmethod
    def is_url_match(cls, url):
        return any(patt in url for patt in cls.URL_PATTERNS)
    async def extract_metadata(self, html): return {}
    def confidence(self, meta): return 80
    def fingerprint(self, resp, text):  # OBRIGATÓRIO implementar fingerprint real!
        return resp.status == 200 and len(text) > 100 and not detect_challenge(text)

class GitHubExtractor(BaseExtractor):
    SITE_NAME = "GitHub"
    URL_PATTERNS = ["github.com"]
    async def extract_metadata(self, html):
        soup = BeautifulSoup(html, "lxml")
        meta = {}
        bio = soup.find("div", class_="p-note user-profile-bio")
        company = soup.find("li", class_="vcard-detail")
        avatar = soup.find("img", class_="avatar-user")
        meta['bio'] = bio.text.strip() if bio else ""
        meta['company'] = company.text.strip() if company else ""
        meta['avatar_url'] = avatar['src'] if avatar else ""
        meta['lang_bio'] = detect_lang(meta['bio'])
        return meta
    def fingerprint(self, resp, text):
        # Verifica por elemento específico de perfil (robusto a challenge/rate)
        soup = BeautifulSoup(text, "lxml")
        if soup.find("meta", {"property": "og:title"}):
            return True
        if soup.find(attrs={"itemprop": "additionalName"}):
            return True
        return False

    def confidence(self, meta):
        c = 70
        if meta.get("bio"): c += 10
        if meta.get("company"): c += 10
        return c

class InstagramExtractor(BaseExtractor):
    SITE_NAME = "Instagram"
    URL_PATTERNS = ["instagram.com"]
    async def extract_metadata(self, html):
        soup = BeautifulSoup(html, "lxml")
        metadata = {}
        # Hydration JSON approach!
        hydration = None
        for script in soup.find_all("script"):
            if script.string and "profilePage_" in script.string:
                m = re.search(r"window\._sharedData\s*=\s*({.*});", script.string)
                if m:
                    hydration = m.group(1)
                    break
            if script.string and 'application/ld+json' in script.get('type', ''):
                hydration = script.string
                break
        user_data = {}
        if hydration:
            try:
                data = json.loads(hydration)
                if 'entry_data' in data and 'ProfilePage' in data['entry_data']:
                    user_data = data['entry_data']['ProfilePage'][0]['graphql']['user']
                elif '@type' in data and data.get("@type") == "Person":
                    user_data = data
            except Exception:
                pass
        if user_data:
            metadata = {
                "full_name": user_data.get("full_name", ""),
                "bio": user_data.get("biography", "") or user_data.get("description", ""),
                "followers": user_data.get("edge_followed_by", {}).get("count", 0),
                "avatar_url": user_data.get("profile_pic_url", user_data.get("image", "")),
            }
            metadata['lang_bio'] = detect_lang(metadata.get("bio", ""))
            return metadata
        # fallback básico
        meta_tag = soup.find("meta", property="og:description")
        if meta_tag:
            metadata["bio"] = meta_tag.get("content", "")
            metadata["lang_bio"] = detect_lang(metadata["bio"])
        return metadata
    def fingerprint(self, resp, text):
        # OBRIGATÓRIO: não aceitar challenge page!
        if detect_challenge(text):
            return False
        soup = BeautifulSoup(text, "lxml")
        # Busca JSON hydration v2
        if '"profilePage_' in text or '"graphql": {' in text:
            return True
        if soup.find("meta", {"property": "og:title"}): return True
        if soup.title and "Instagram" in soup.title.text:
            return True
        return False
    def confidence(self, meta):
        return 70 if meta.get("bio") else 40

class RedditExtractor(BaseExtractor):
    SITE_NAME = "Reddit"
    URL_PATTERNS = ["reddit.com"]
    async def extract_metadata(self, html):
        soup = BeautifulSoup(html, "lxml")
        karma = soup.find("span", class_=re.compile("karma"))
        bio = soup.find("div", class_="bio")
        avatar = soup.find("img", class_="ProfileSidebar__avatar")
        return {
            "karma": karma.text.strip() if karma else "",
            "bio": bio.text.strip() if bio else "",
            "avatar_url": avatar['src'] if avatar else "",
        }
    def fingerprint(self, resp, text):
        if detect_challenge(text): return False
        soup = BeautifulSoup(text, "lxml")
        if soup.find("div", class_="ProfileSidebar"):
            return True
        return False

class TwitterExtractor(BaseExtractor):
    SITE_NAME = "Twitter"
    URL_PATTERNS = ["twitter.com", "x.com"]
    async def extract_metadata(self, html):
        soup = BeautifulSoup(html, "lxml")
        title = soup.find("title")
        desc = soup.find("meta", attrs={"name": "description"})
        avatar = soup.find("img", src=re.compile("profile_images"))
        return {
            "title": title.text.strip() if title else "",
            "description": desc["content"] if desc else "",
            "avatar_url": avatar['src'] if avatar else "",
        }
    def fingerprint(self, resp, text):
        if detect_challenge(text): return False
        soup = BeautifulSoup(text, "lxml")
        if soup.find(string=re.compile("hasn't tweeted")):
            return False
        if "UserUnavailable" in text:
            return False
        if "followers" in text and "Following" in text:
            return True
        return False
    def confidence(self, meta):
        return 60 + (10 if meta.get("description") else 0)

class GravatarExtractor(BaseExtractor):
    SITE_NAME = "Gravatar"
    URL_PATTERNS = ["gravatar.com"]
    # Placeholder para futuro extractor

EXTRACTORS = {
    "GitHub": GitHubExtractor(),
    "Instagram": InstagramExtractor(),
    "Twitter": TwitterExtractor(),
    "Reddit": RedditExtractor(),
}

SITES = {
    "GitHub": "https://github.com/{}",
    "Instagram": "https://www.instagram.com/{}/",
    "Twitter": "https://twitter.com/{}",
    "Reddit": "https://www.reddit.com/user/{}",
}

SITE_BY_URL = []
for name, extractor in EXTRACTORS.items():
    for pattern in extractor.URL_PATTERNS:
        SITE_BY_URL.append((pattern, name))

def find_extractor_for_url(url):
    for patt, sitename in SITE_BY_URL:
        if patt in url:
            return EXTRACTORS[sitename]
    return None

async def try_avatar_hash(url):
    try:
        session = await HTTPSessionPool.get()
        async with session.get(url, headers=random_stealth_headers(), allow_redirects=True) as resp:
            if resp.status == 200:
                img_bytes = await resp.read()
                percept, md5val = hash_avatar(img_bytes)
                return percept or md5val
    except Exception:
        return None

# ---------- Passive Intelligence Engine (dorks via Bing, etc.) ---------
class PassiveIntelEngine:
    def __init__(self, username, engines=("bing",), dork_mode="multi"):
        self.username = username
        self.engines = engines
        self.dork_mode = dork_mode
        self.rate_limit_sec = CONFIG.get("passive_rate_limit_sec", 5)
        self.session = None

    def build_bing_dorks(self):
        # Pode fazer variantes, bio, comentários, links, etc.
        user = self.username
        dorks = [
            f'site:instagram.com "{user}"',
            f'site:github.com "{user}"',
            f'site:twitter.com "{user}"',
            f'site:reddit.com "{user}"',
            # Com contexto:
            f'site:instagram.com "{user}" "@"',
            f'site:instagram.com "{user}" "/p/"',
            f'site:instagram.com "{user}" "comentou"',
            f'site:instagram.com "{user}" "bio"',
            f'site:twitter.com "{user}" "@"',
        ]
        return dorks[:8]

    async def run(self):
        results = []
        session = await HTTPSessionPool.get()
        # Rate limit ativo
        last_req = [0.0]
        # Multi-engine support no futuro
        for engine in self.engines:
            if engine == "bing":
                dorks = self.build_bing_dorks()
                for q in dorks:
                    # Obedece rate limit + jitter!
                    now = time.time()
                    delta = now - last_req[0]
                    min_wait = self.rate_limit_sec + random.uniform(0.3, 0.9)
                    if delta < min_wait:
                        await asyncio.sleep(min_wait - delta)
                    last_req[0] = time.time()
                    # -- CACHE
                    pcache = await passive_cache_get(engine, q, self.username)
                    if pcache:
                        snippets = pcache["snippets"]
                        score = pcache["score"]
                        results.append({"engine": engine, "dork": q, "snippets": snippets, "score": score, "cache": True})
                        continue
                    for retry in range(CONFIG.get("max_retries",2)+1):
                        try:
                            # Bing classic web search v2
                            url = f"https://www.bing.com/search?q={q.replace(' ', '+')}&count=7"
                            async with session.get(url, headers=random_stealth_headers(), timeout=CONFIG["timeout"], allow_redirects=True) as resp:
                                bing_html = await resp.text()
                                if detect_challenge(bing_html):
                                    console.print(f"[red][PASSIVE] Bing challenge detected, cooldown triggered![/red]")
                                    await asyncio.sleep(30 + random.randint(5, 25))
                                    continue
                                snippets = self.parse_bing_results(bing_html)
                                score = self.passive_score(snippets)
                                await passive_cache_set(engine, q, self.username, snippets, score)
                                results.append({"engine": engine, "dork": q, "snippets": snippets, "score": score, "cache": False})
                                break
                        except asyncio.TimeoutError:
                            if retry == CONFIG.get("max_retries", 2):
                                results.append({"engine": engine, "dork": q, "snippets": [], "score": 0, "error": "timeout"})
                        except Exception as e:
                            if retry == CONFIG.get("max_retries", 2):
                                results.append({"engine": engine, "dork": q, "snippets": [], "score": 0, "error": str(e)})
                        await asyncio.sleep(2 ** retry + random.uniform(0, 0.8))
        return results

    def parse_bing_results(self, html):
        soup = BeautifulSoup(html, "lxml")
        snippet_blocks = soup.find_all("li", {"class": "b_algo"})
        results = []
        for blk in snippet_blocks:
            link = blk.find("a")
            href = link["href"] if link else ""
            title = link.text.strip() if link else ""
            descr = blk.find("p").text.strip() if blk.find("p") else ""
            context = blk.text.strip()
            results.append({"title": title, "link": href, "desc": descr, "context": context})
        return results

    def passive_score(self, results):
        # Score contextual: presença, contexto, plataforma, bio...
        score = 0
        user = self.username.lower()
        for r in results:
            c = r["context"].lower()
            s = 0
            if user in c:
                s += 10
            if "instagram.com/p/" in c: s += 10
            if "bio" in c: s += 12
            if "comment" in c or "comentou" in c: s += 10
            if "@" + user in c: s += 8
            if "followers" in c: s += 4
            if "avatar" in c: s += 5
            if "twitter.com/" in c: s += 5
            if s == 0:
                if user in r["desc"].lower():
                    s = 8
            score += s
        # Muito baixo = ruído
        return min(100, score)

    def rich_show(self, passive_results):
        table = Table(title="Passive OSINT (Bing)", box=box.ROUNDED)
        table.add_column("Dork", justify="left")
        table.add_column("Score", justify="center")
        table.add_column("Top Link / Context")
        for r in passive_results:
            dork = r.get('dork', '')[:38] + ('...' if len(r.get('dork', '')) > 38 else "")
            score = f"{r['score']}"
            top = r['snippets'][0]['link'] if r['snippets'] else "-"
            ctx = r['snippets'][0]['context'][:70] if r['snippets'] else "-"
            table.add_row(dork, score, f"{top}\n{ctx}")
        console.print(table)

    def enrich_metadata(self, meta, passive_results):
        # Enrich meta com score passivo geral
        best = max([r["score"] for r in passive_results if r.get("score", 0)], default=0)
        meta = dict(meta)
        meta["passive_score"] = best
        return meta

# ------------- SCAN DE PERFIL PRINCIPAL (corrigido: sem fechar sess pool)
async def scan_single(username, site, url_tmpl, sem: asyncio.Semaphore):
    async with sem:
        jitter = random.uniform(*[v/1000 for v in CONFIG.get("sem_delay_ms", [300, 2000])])
        if CONFIG.get("stealth"):
            await asyncio.sleep(jitter)
        cached = await cache_get(username, site)
        if cached and cached.get("status") == "FOUND" and cached.get("last_check"):
            return {**cached, "username": username}
        session = await HTTPSessionPool.get()
        ex = EXTRACTORS[site]
        target_url = url_tmpl.format(username)
        found = False
        meta = None
        hashval = None
        for retry in range(CONFIG.get("max_retries",2)+1):
            try:
                async with session.get(target_url, headers=random_stealth_headers(), allow_redirects=True) as resp:
                    text = await resp.text()
                    found = ex.fingerprint(resp, text)
                    meta = await ex.extract_metadata(text) if found else {}
                    avatar_url = extract_avatar_url(meta)
                    if avatar_url:
                        hashval = await try_avatar_hash(avatar_url)
                    profile = {
                        "site": site,
                        "url": target_url,
                        "status": "FOUND" if found else "NOT FOUND",
                        "metadata": meta,
                        "avatar_hash": hashval,
                        "username": username,
                        "confidence": ex.confidence(meta)
                    }
                    if found:
                        await cache_set(username, site, target_url, 1, profile["confidence"], hashval, meta)
                    return profile
            except Exception as e:
                if retry == CONFIG.get("max_retries",2):
                    console.print(f"[red][ERROR {site}] {e}")
            await asyncio.sleep(2 ** retry + random.uniform(0, 1))
        return None

# ------------- CLI: agora aceita --passive (coleta dorks) -------------
async def scan_username(username, mode="single", email=None, passive=False):
    found_profiles = []
    variants = [username] if mode == "single" else smart_username_variants(username)
    sem = HTTPSessionPool.get_sem()
    tasks = []
    for uname in variants:
        for site, url_tmpl in SITES.items():
            tasks.append(scan_single(uname, site, url_tmpl, sem))
    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Scanning...", total=len(tasks))
        for coro in asyncio.as_completed(tasks):
            prof = await coro
            if prof:
                found_profiles.append(prof)
            progress.advance(task)
    passive_results = []
    if passive:
        passive_engine = PassiveIntelEngine(username)
        passive_results = await passive_engine.run()
        PassiveIntelEngine(username).rich_show(passive_results)
        # Enrich metadata in-place (só no profile principal)
        if found_profiles:
            for prof in found_profiles:
                prof["metadata"] = passive_engine.enrich_metadata(prof.get("metadata", {}), passive_results)
    await HTTPSessionPool.close()
    return found_profiles, passive_results

def rich_summary(profiles, onlyfound=False, min_conf=0):
    table = Table(title="ShadowTrace OSINT", box=box.DOUBLE)
    table.add_column("Platform", justify="left")
    table.add_column("Username")
    table.add_column("Found", justify="center")
    table.add_column("Confidence")
    table.add_column("Lang")
    table.add_column("Avatar Hash")
    table.add_column("Profile Link")
    for profile in profiles:
        found = profile.get("status") == "FOUND"
        if onlyfound and not found: continue
        if profile.get("confidence",0) < min_conf: continue
        found_text = "[green]YES" if found else "[red]NO"
        conf = f"{profile.get('confidence',0)}%"
        avatar = profile.get("avatar_hash") or "-"
        link = f"[blue underline]{profile['url']}[/blue underline]"
        lang = profile.get("metadata", {}).get("lang_bio") or "-"
        table.add_row(profile["site"], profile["username"], found_text, conf, lang, avatar, link)
    console.print(table)

def filter_profiles(profiles, onlyfound=False, min_confidence=0):
    return [p for p in profiles
            if (not onlyfound or p.get("status")=="FOUND")
            and p.get("confidence",0) >= min_confidence]

def export_json(profiles, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(profiles, f, indent=2)
    console.print(f"[green]Exported to {path}")

def export_csv(profiles, path):
    if not profiles: return
    fieldnames = ["site", "username", "url", "status", "confidence", "avatar_hash", "metadata"]
    with open(path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in profiles:
            data = dict(row)
            data['metadata'] = json.dumps(data.get('metadata', {}))
            writer.writerow(data)
    console.print(f"[green]CSV saved at {path}")

def export_html(profiles, path):
    html = """
    <html><head>
    <style>
    body { font-family: Arial; background: #eee; }
    .profile { background: #fff; margin:1em; padding:1em; border-radius:8px;}
    .found { color: green }
    .notfound { color: red }
    </style>
    </head><body>
    <h1>ShadowTrace OSINT Report</h1>
    """
    for p in profiles:
        found = "FOUND" if p.get("status") == "FOUND" else "NOT FOUND"
        html += f"""
        <div class="profile">
        <b>Site:</b> {p['site']}<br>
        <b>Username:</b> {p['username']}<br>
        <b>Status:</b> <span class="{found.lower()}">{found}</span> <br>
        <b>Confidence:</b> {p.get('confidence',0)}%<br>
        <b>Avatar hash:</b> {p.get('avatar_hash','')}<br>
        <b>Lang:</b> {p.get('metadata',{{}}).get('lang_bio','')}<br>
        <b>Profile:</b> <a href="{p['url']}">{p['url']}</a><br>
        <b>Metadata:</b><pre>{json.dumps(p.get('metadata',{}),indent=2)}</pre>
        </div>
        """
    html += "</body></html>"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    console.print(f"[green]HTML report saved as {path}")

def export_graphml(profiles, path):
    nodes = {}
    edges = set()
    for prof in profiles:
        uname, site = prof['username'], prof['site']
        nid = f"{uname}@{site}"
        nodes[nid] = {"label":nid, "avatar":prof.get('avatar_hash',''), "bio":prof.get('metadata',{}).get("bio","")}
        nodes[site] = {"label": site}
        edges.add((nid, site, "on"))
    for a in profiles:
        for b in profiles:
            if a is b: continue
            if a.get("avatar_hash") and a["avatar_hash"] == b.get("avatar_hash") and a["site"] != b["site"]:
                edges.add((f"{a['username']}@{a['site']}", f"{b['username']}@{b['site']}", "same_avatar"))
    with open(path, 'w', encoding="utf-8") as f:
        f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
<graph id="ShadowTrace" edgedefault="undirected">""")
        for nid, data in nodes.items():
            f.write(f'<node id="{nid}"><data key="label">{data["label"]}</data></node>\n')
        for src, tgt, typ in edges:
            f.write(f'<edge source="{src}" target="{tgt}"><data key="type">{typ}</data></edge>\n')
        f.write("</graph></graphml>")
    console.print(f"[green]GraphML export ready: {path}")

def banner():
    console.print(Panel.fit("""
ShadowTrace v3.0+ 🚀 [light_blue]ADVANCED MODE[/light_blue]
[cyan]https://github.com/Misterydo/shadowtrace[/cyan]
Ethical hacking only. CLI by professionals, for professionals.
""", style="magenta"))

def help_menu():
    console.print("""
[bold cyan]Commands:[/bold cyan]
- scan <username>           Scan username at all platforms
- scan -v <username>        Scan username variants
- scan --passive <username> Passive search with OSINT dorks (Google/Bing)
- scan --found              Show only found after last scan
- scan --conf <n>           Show only found with confidence n+
- export <file.json>        Export last result to JSON
- export-csv <file.csv>     Export last result to CSV
- export-html <file.html>   Export last result to HTML
- export-graphml <file.graphml>   Export nodes/edges for Gephi/Neo4j
- set mode [passive|agg]    Set scan mode
- set tor [on|off]          Enable Tor proxy mode
- set threads <n>           Set concurrency
- clear                     Clear terminal
- exit                      Exit
""")

async def shutdown():
    await HTTPSessionPool.close()
    await GlobalDB.close()

async def main():
    banner()
    last_profiles = []
    last_passive = []
    try:
        while True:
            try:
                cmdinput = console.input("[magenta]ShadowTrace > [/magenta]").strip()
                if not cmdinput:
                    continue
                if cmdinput in ("exit", "quit"):
                    await shutdown()
                    return  # Encerra o main async corretamente
                elif cmdinput == 'help':
                    help_menu()
                elif cmdinput.startswith("scan"):
                    args = cmdinput.split()
                    username = None
                    mode = "single"
                    only_found = False
                    min_conf = 0
                    passive = False
                    if "--passive" in args:
                        passive = True
                        idx = args.index("--passive")
                        if len(args) > idx+1:
                            username = args[idx+1]
                        else:
                            console.print("[yellow]Usage: scan --passive username[/yellow]")
                            continue
                    elif "-v" in args:
                        mode = "variants"
                        username = args[args.index("-v")+1]
                    elif len(args) > 1:
                        username = args[1]
                    if not username:
                        console.print("[red]Missing username. Ex: scan --passive YOURUSER")
                        continue
                    if "--found" in args:
                        only_found = True
                    if "--conf" in args:
                        idx = args.index("--conf")
                        if len(args) > idx+1:
                            min_conf = int(args[idx+1])
                    (res, passive_out) = await scan_username(username, mode, passive=passive)
                    last_profiles = res
                    last_passive = passive_out
                    if not res or all(p.get('status') != "FOUND" for p in res):
                        console.print("\n[bold yellow]Nenhum perfil encontrado nas plataformas principais.[/bold yellow]\n")
                        for p in res:
                            debug_data = f" {p['site']} → status={p.get('status')}, meta={p.get('metadata')}"
                            console.print(debug_data)
                            if "error" in p:  # Se scan_username algum dia passar esse campo
                                console.print(f"[red]Erro: {p['error']}")
                    rich_summary(res, onlyfound=only_found, min_conf=min_conf)
                    if len(res) > 1:
                        cscore = correlation_score(res)
                        console.print(f"[yellow]Identity Correlation Score: {cscore}%[/yellow]")
                    if passive_out:
                        PassiveIntelEngine(username).rich_show(passive_out)
                elif cmdinput.startswith("export "):
                    export_json(last_profiles, cmdinput.split()[1])
                elif cmdinput.startswith("export-csv "):
                    export_csv(last_profiles, cmdinput.split()[1])
                elif cmdinput.startswith("export-html "):
                    export_html(last_profiles, cmdinput.split()[1])
                elif cmdinput.startswith("export-graphml "):
                    export_graphml(last_profiles, cmdinput.split()[1])
                elif cmdinput.startswith("set mode"):
                    m = cmdinput.split()[2]
                    CONFIG["mode"] = m
                    console.print(f"[cyan]Mode set to {m}")
                elif cmdinput.startswith("set tor"):
                    v = cmdinput.split()[2]
                    CONFIG["tor"] = (v == 'on')
                    console.print("[cyan]Tor mode enabled!" if CONFIG["tor"] else "[cyan]Tor disabled!")
                elif cmdinput.startswith("set threads"):
                    t = int(cmdinput.split()[2])
                    CONFIG["threads"] = t
                    HTTPSessionPool.semaphore = asyncio.Semaphore(t)
                    console.print(f"[cyan]Threads: {t}")
                elif cmdinput == "clear":
                    os.system("clear" if os.name != "nt" else "cls")
                    banner()
                else:
                    console.print("[red]Unknown command. Type 'help'")
            except KeyboardInterrupt:
                console.print("[red]\nInterrupted!")
                await shutdown()
                sys.exit(0)
            except Exception as e:
                console.print(f"[red][Broke] {e}")
    finally:
        await shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass














