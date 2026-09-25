# -*- coding: utf-8 -*-
"""
Lookup Tool - GUI + Shared Core
Abfragen: IP, E-Mail, Benutzername, Domain, Snapchat, Account-View
Nur öffentliche Daten / Legal-APIs. Ergebnisse sind ggf. Schätzungen.
Keine Logins, keine Tokens, keine "Steal"-Funktionen.
"""
import html
import json
import os
import queue
import random
import re
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from tkinter import ttk, filedialog, messagebox

VER = "2.7"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LookupTool/1.0"}
TIMEOUT = 10

DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "temp-mail.org", "yopmail.com", "sharklasers.com", "throwawaymail.com",
    "getnada.com", "maildrop.cc", "trashmail.com", "fakeinbox.com",
}

USERNAME_SITES = [
    ("GitHub",       "https://github.com/{u}"),
    ("Reddit",       "https://www.reddit.com/user/{u}"),
    ("Twitch",       "https://www.twitch.tv/{u}"),
    ("Pinterest",    "https://www.pinterest.com/{u}/"),
    ("SoundCloud",   "https://soundcloud.com/{u}"),
    ("Medium",       "https://medium.com/@{u}"),
    ("Dev.to",       "https://dev.to/{u}"),
    ("Steam",        "https://steamcommunity.com/id/{u}"),
    ("Roblox",       "https://www.roblox.com/users/profile?username={u}"),
    ("About.me",     "https://about.me/{u}"),
    ("Linktree",     "https://linktr.ee/{u}"),
    ("TikTok",       "https://www.tiktok.com/@{u}"),
    ("YouTube",      "https://www.youtube.com/@{u}"),
    ("Instagram",    "https://www.instagram.com/{u}/"),
    ("X (Twitter)",  "https://x.com/{u}"),
    ("Facebook",     "https://www.facebook.com/{u}"),
]

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


# ---------------------------------------------------------------- DNS (roh)
def _decode_name(data, pos):
    labels, jumped, orig = [], False, pos
    while True:
        if pos >= len(data):
            break
        length = data[pos]
        if length == 0:
            pos += 1
            break
        if (length & 0xC0) == 0xC0:
            if pos + 1 >= len(data):
                break
            ptr = ((length & 0x3F) << 8) | data[pos + 1]
            if not jumped:
                orig = pos + 2
            jumped, pos = True, ptr
        else:
            pos += 1
            labels.append(data[pos:pos + length].decode("utf-8", "replace"))
            pos += length
    return ".".join(labels), (orig if jumped else pos)


def _doh_query(name, qtype):
    """Fallback: DNS-over-HTTPS (Cloudflare), funktioniert auch hinter VPN/Firewalls."""
    import urllib.parse
    tnames = {1: "A", 2: "NS", 5: "CNAME", 15: "MX", 16: "TXT"}
    url = ("https://cloudflare-dns.com/dns-query?name="
           + urllib.parse.quote(name) + "&type=" + tnames.get(qtype, str(qtype)))
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/dns-json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    out = []
    for a in d.get("Answer") or []:
        if a.get("type") != qtype:
            continue
        data = str(a.get("data", "")).rstrip(".")
        if qtype == 16:  # TXT in Anführungszeichen
            data = data.strip('"')
        out.append(data)
    return out


def dns_query(name, qtype, server="1.1.1.1"):
    """Minimaler DNS-Client mit DoH-Fallback. qtype: 1=A, 2=NS, 15=MX, 16=TXT."""
    try:
        return _dns_udp(name, qtype, server)
    except Exception:
        return _doh_query(name, qtype)


def _dns_udp(name, qtype, server):
    tid = b"\x12\x34"
    flags = b"\x01\x00"
    counts = struct.pack(">HHHH", 1, 0, 0, 0)
    q = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
    q += struct.pack(">HH", qtype, 1)
    packet = tid + flags + counts + q
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3)  # kurz - danach schneller DoH-Fallback
    try:
        sock.sendto(packet, (server, 53))
        data, _ = sock.recvfrom(4096)
    finally:
        sock.close()
    if len(data) < 12:
        return []
    qd, an = struct.unpack(">HH", data[4:8])
    pos = 12
    for _ in range(qd):
        _, pos = _decode_name(data, pos)
        pos += 4
    results = []
    for _ in range(an):
        _, pos = _decode_name(data, pos)
        if pos + 10 > len(data):
            break
        rtype, _, rdlen = struct.unpack(">HHH", data[pos:pos + 6])
        pos += 6
        rdata = data[pos:pos + rdlen]
        pos += rdlen
        if rtype == 1 and rdlen == 4:
            results.append(socket.inet_ntoa(rdata))
        elif rtype == 2:
            n, _ = _decode_name(data, pos - rdlen)
            results.append(n)
        elif rtype == 15 and rdlen > 2:
            n, _ = _decode_name(data, pos - rdlen + 2)
            results.append(f"{struct.unpack('>H', rdata[:2])[0]} {n}")
        elif rtype == 5:
            n, _ = _decode_name(data, pos - rdlen)
            results.append("CNAME -> " + n)
        elif rtype == 16:
            # TXT: Liste von Länge-prefix-Strings
            parts, i = [], 0
            while i < rdlen:
                ln = rdata[i]
                parts.append(rdata[i + 1:i + 1 + ln].decode("utf-8", "replace"))
                i += 1 + ln
            results.append("".join(parts))
    return results


# ---------------------------------------------------------------- HTTP-Helper
def http_json(url, method="GET"):
    req = urllib.request.Request(url, headers=UA, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def http_status(url, method="GET"):
    req = urllib.request.Request(url, headers=UA, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


# ---------------------------------------------------------------- Lookups
def lookup_ip(query):
    url = "https://ipwho.is/" + (query.strip() if query.strip() else "")
    d = http_json(url)
    if not d.get("success", True):
        raise ValueError(d.get("message", "Unbekannter Fehler"))
    out = [("IP-Adresse", d.get("ip")),
           ("Typ", d.get("type")),
           ("Kontinent", d.get("continent")),
           ("Land", f'{d.get("country")} ({d.get("country_code")})'),
           ("Region", d.get("region")),
           ("Stadt", f'{d.get("city")} {d.get("postal")}'),
           ("Koordinaten", f'{d.get("latitude")}, {d.get("longitude")}') ,
           ("Zeitzone", d.get("timezone", {}).get("id") if isinstance(d.get("timezone"), dict) else d.get("timezone")),
           ("ISP / Anbieter", d.get("connection", {}).get("isp") if isinstance(d.get("connection"), dict) else None),
           ("Organisation", d.get("connection", {}).get("org") if isinstance(d.get("connection"), dict) else None),
           ("ASN", d.get("connection", {}).get("asn") if isinstance(d.get("connection"), dict) else None)]
    return out


def lookup_email(email):
    email = email.strip()
    out = []
    if not EMAIL_RE.match(email):
        out.append(("Syntax", "FEHLER - ungültiges E-Mail-Format"))
        return out
    out.append(("Syntax", "OK"))
    domain = email.split("@")[1].lower()
    out.append(("Domain", domain))
    out.append(("Disposable / Wegwerf", "JA (vermutlich)" if domain in DISPOSABLE else "Nein (Bekannte Liste)"))
    try:
        socket.getaddrinfo(domain, 80)
        out.append(("Domain erreichbar (A)", "Ja"))
    except Exception:
        out.append(("Domain erreichbar (A)", "Nein - Domain existiert nicht / nicht auflösbar"))
        return out
    try:
        mx = dns_query(domain, 15)
        out.append(("MX-Server", ", ".join(mx) if mx else "KEINE - E-Mails werden nicht empfangen"))
    except Exception as e:
        out.append(("MX-Server", f"Abfrage fehlgeschlagen ({e})"))
    try:
        txt = dns_query(domain, 16)
        spf = [t for t in txt if t.lower().startswith("v=spf1")]
        out.append(("SPF-Eintrag", spf[0][:120] if spf else "Kein SPF-Eintrag (weniger vertrauenswürdig)"))
    except Exception:
        pass
    return out


def lookup_username(username):
    username = username.strip().lstrip("@")
    if not re.match(r"^[A-Za-z0-9_.\-]{1,32}$", username):
        raise ValueError("Ungültiger Benutzername (erlaubt: a-z 0-9 _ . -)")
    out = []
    for name, tmpl in USERNAME_SITES:
        code = http_status(tmpl.format(u=username))
        if code == 200:
            status = "[gefunden]"
        elif code in (404, 410):
            status = "[nicht gefunden]"
        elif code in (401, 403, 429):
            status = "[blockiert / nicht pruefbar]"
        elif code is None:
            status = "[Fehler / Timeout]"
        else:
            status = f"[HTTP {code}]"
        out.append((name, status))
    return out


def lookup_domain(domain):
    domain = domain.strip().lower().rstrip(".")
    if not re.match(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$", domain):
        raise ValueError("Ungültige Domain")
    out = [("Domain", domain)]
    # DNS
    for label, qt in (("A", 1), ("NS", 2), ("MX", 15)):
        try:
            res = dns_query(domain, qt)
            out.append((f"DNS {label}", ", ".join(res) if res else "keine Einträge"))
        except Exception as e:
            out.append((f"DNS {label}", f"Fehler ({e})"))
    # RDAP (öffentliche WHOIS-Alternative)
    try:
        d = http_json("https://rdap.org/domain/" + domain)
        out.append(("Registrar", _rdap_registrar(d)))
        out.append(("Status", ", ".join(d.get("status", [])) or "-"))
        events = {e.get("eventAction"): e.get("eventDate") for e in d.get("events", [])}
        out.append(("Registriert", events.get("registration", "-")))
        out.append(("Läuft ab", events.get("expiration", "-")))
        out.append(("Aktualisiert", events.get("last update of RDAP database", events.get("last-updateof rdap database", "-"))))
        nameservers = [n.get("ldhName") for n in d.get("nameservers", [])]
        if nameservers:
            out.append(("Nameserver", ", ".join(nameservers)))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            out.append(("RDAP / WHOIS", "Domain nicht registriert (404)"))
        else:
            out.append(("RDAP / WHOIS", f"HTTP {e.code}"))
    except Exception as e:
        out.append(("RDAP / WHOIS", f"Fehler ({e})"))
    return out


def _rdap_registrar(d):
    for ent in d.get("entities", []):
        roles = ent.get("roles", [])
        if "registrar" in roles:
            for item in ent.get("vcardArray", [None, []])[1]:
                if item and item[0] == "fn":
                    return item[3]
            return ent.get("handle", "-")
    return "-"


def fmt(out):
    width = max(len(k) for k, _ in out)
    return "\n".join(f"{k.ljust(width)}  {v}" for k, v in out if v is not None)


# ------------------------------------------- Browser-Fetch (nur GET/oeffentlich)
NAV_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


def _fetch_html(url, timeout=8, read_limit=300000, headers=None):
    """Seite wie ein Browser holen -> (text, status). Bei Zertifikats-
    fehlern einmal unverifiziert wiederholen ( weiterhin nur GET)."""
    hdrs = dict(NAV_HEADERS)
    if headers:
        hdrs.update(headers)
    for attempt in (0, 1):
        ctx = (ssl.create_default_context() if attempt == 0
               else ssl._create_unverified_context())
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read(read_limit).decode("utf-8", "replace"), r.status
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read(6000).decode("utf-8", "replace")
            except Exception:
                pass
            return body, e.code
        except Exception as ex:
            msg = str(ex).upper()
            if attempt == 0 and ("CERTIFICATE" in msg or "SSL" in msg):
                continue
            raise ValueError(f"Nicht erreichbar: {type(ex).__name__}: {ex}")
    raise ValueError("Nicht erreichbar")


def _meta(body, prop):
    """Inhalt eines meta-Tags (Attribut-Reihenfolge egal, HTML-Entities raus)."""
    esc = re.escape(prop)
    m = (re.search(r'property=["\']' + esc + r'["\']\s+content=["\']([^"\']*)',
                   body)
         or re.search(r'content=["\']([^"\']*)["\']\s+property=["\']' + esc,
                      body)
         or re.search(r'name=["\']' + esc + r'["\']\s+content=["\']([^"\']*)',
                      body))
    return html.unescape(m.group(1)).strip() if m else ""


# ------------------------------------------------------- Snapchat (oeffentlich)
def _snap_fetch(q):
    """Add-Profil holen -> (body, status)."""
    return _fetch_html(f"https://www.snapchat.com/add/{q}", timeout=10,
                       read_limit=300000)


def _snap_name(body):
    """Anzeigename aus og:title oder Profil-Header ziehen."""
    title = _meta(body, "og:title") or ""
    name = title
    for suf in (" auf Snapchat", " on Snapchat"):
        if name.endswith(suf):
            name = name[:-len(suf)].strip()
    m = re.search(
        r'data-testid="publicProfileDisplayName".{0,400}?'
        r'<span[^>]*>([^<]+)</span>', body, re.S)
    if m:
        name = html.unescape(m.group(1)).strip() or name
    return name


def lookup_snapchat(username):
    """Oeffentliches Snapchat-Add-Profil: Anzeigename, Beschreibung,
    Profil-URL, Vorschaubild. Kein Login, keine privaten Daten, kein Steal."""
    q = (username or "").strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,25}", q):
        raise ValueError("Ungueltiger Snapchat-Username (a-z, 0-9, . _ -)")
    url = f"https://www.snapchat.com/add/{q}"
    body, st = _snap_fetch(q)
    if st == 404:
        return [("Username", "@" + q),
                ("Status", "nicht gefunden (404)"),
                ("Hinweis", "Snapchat zeigt nur oeffentliche Add-Profile"),
                ("Pruefen", url)]
    if st in (401, 403, 429, 451):
        return [("Username", "@" + q),
                ("Status", f"gesperrt (HTTP {st}) - Bot-/VPN-Schutz"),
                ("Pruefen", url)]
    if st != 200:
        raise ValueError(f"Snapchat: unerwarteter Status {st}")
    desc = _meta(body, "og:description")
    return [
        ("Username", "@" + q),
        ("Anzeigename", _snap_name(body) or "-"),
        ("Beschreibung", desc or "-"),
        ("Profil-URL", _meta(body, "og:url") or url),
        ("Vorschaubild", _meta(body, "og:image") or "-"),
        ("Status", "oeffentliches Add-Profil gefunden"),
        ("Quelle", "snapchat.com - oeffentlich, kein Login"),
    ]


# --------------------------------------------------- Account-View (oeffentlich)
def _acct_og(url, missing=None, timeout=6):
    """og:title/-description als Kurzdetail, inkl. Status-Ehrlichkeit."""
    body, st = _fetch_html(url, timeout=timeout, read_limit=220000)
    if st == 404:
        return "nicht gefunden (404)"
    if st in (401, 403, 429, 451):
        return f"gesperrt (HTTP {st}) - evtl. VPN/Bot-Schutz"
    if st != 200:
        return f"unerwartet (HTTP {st})"
    title = _meta(body, "og:title")
    if missing and missing(title, body):
        return "nicht gefunden"
    if not title:
        return "kein oeffentlicher Zugriff (Login/JS noetig)"
    desc = _meta(body, "og:description")
    out = title
    if desc and desc.strip() and desc.strip() != title.strip():
        out += " - " + desc[:70]
    return out


def _acct_github(u):
    body, st = _fetch_html(
        f"https://api.github.com/users/{u}", timeout=6, read_limit=80000,
        headers={"User-Agent": "LookupTool/2.6",
                 "Accept": "application/vnd.github+json"})
    if st == 404:
        return "nicht gefunden (404)"
    if st != 200:
        return f"HTTP {st}" + (" - Rate-Limit (60/h ohne Login)" if st == 403
                               else "")
    try:
        d = json.loads(body)
    except Exception:
        return "Antwort unlesbar"
    parts = []
    if d.get("name"):
        parts.append(str(d["name"]))
    parts.append(f"{d.get('public_repos', 0)} Repos")
    parts.append(f"{d.get('followers', 0)} Follower")
    if d.get("created_at"):
        parts.append("seit " + str(d["created_at"])[:10])
    if d.get("bio"):
        parts.append(str(d["bio"])[:60])
    return " | ".join(p for p in parts if p)


def _acct_reddit(u):
    body, st = _fetch_html(
        f"https://www.reddit.com/user/{u}/about.json", timeout=6,
        read_limit=120000,
        headers={"User-Agent": "LookupTool/2.6 (public profile check)",
                 "Accept": "application/json"})
    if st == 404:
        return "nicht gefunden (404)"
    if st in (401, 403, 429):
        return f"gesperrt (HTTP {st}) - Reddit blockt oft VPN/Daten-IPs"
    if st != 200:
        return f"HTTP {st}"
    try:
        d = json.loads(body).get("data", {})
    except Exception:
        return "Antwort unlesbar"
    created = datetime.fromtimestamp(
        d.get("created_utc", 0), timezone.utc).strftime("%Y-%m-%d")
    out = f"{d.get('total_karma', 0)} Karma, seit {created}"
    bio = ((d.get("subreddit") or {}).get("public_description") or "").strip()
    if bio:
        out += " - " + bio[:60]
    return out


def _acct_telegram(u):
    def miss(t, b):
        return (t.startswith("Telegram: Contact @")
                and not _meta(b, "og:description"))
    return _acct_og(f"https://t.me/{u}", missing=miss)


def _acct_twitch(u):
    return _acct_og(f"https://www.twitch.tv/{u}",
                    missing=lambda t, b: t.strip().lower() in ("twitch",))


def _acct_steam(u):
    return _acct_og(f"https://steamcommunity.com/id/{u}/",
                    missing=lambda t, b: ":: fehler" in t.lower())


def _acct_soundcloud(u):
    return _acct_og(f"https://soundcloud.com/{u}")


def _acct_x(u):
    """X/Twitter: echte Profile liefern Name + Bio, fehlende 404."""
    return _acct_og(f"https://x.com/{u}")


def _acct_ig(u):
    """Instagram zeigt Nicht-Eingeloggten immer dieselbe Login-Wand."""
    body, st = _fetch_html(f"https://www.instagram.com/{u}/", timeout=6,
                           read_limit=60000)
    if st == 404:
        return "nicht gefunden (404)"
    if st in (401, 403, 429):
        return f"gesperrt (HTTP {st})"
    if st != 200:
        return f"HTTP {st}"
    return "nur Login-Wand - ohne Login nicht verifizierbar"


def _snap_detail(q):
    """Kurzdetail fuer die Account-View (gleiche Quelle wie Option 26)."""
    body, st = _snap_fetch(q)
    if st == 404:
        return "nicht gefunden (404)"
    if st in (401, 403, 429):
        return f"gesperrt (HTTP {st})"
    if st != 200:
        return f"HTTP {st}"
    name = _snap_name(body)
    return (name + " - oeffentliches Add-Profil") if name else "gefunden"


def lookup_account_view(username):
    """Account-View: Benutzername gegen Plattformen mit oeffentlich
    auffindbaren Profildaten pruefen (Threads, Nur-Lese)."""
    q = (username or "").strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,32}", q):
        raise ValueError("Ungueltiger Benutzername (a-z 0-9 . _ -)")
    jobs = [
        ("GitHub", lambda: _acct_github(q)),
        ("Snapchat", lambda: _snap_detail(q)),
        ("Telegram", lambda: _acct_telegram(q)),
        ("Twitch", lambda: _acct_twitch(q)),
        ("SoundCloud", lambda: _acct_soundcloud(q)),
        ("Steam", lambda: _acct_steam(q)),
        ("Reddit", lambda: _acct_reddit(q)),
        ("X (Twitter)", lambda: _acct_x(q)),
        ("Instagram", lambda: _acct_ig(q)),
    ]
    vals = [None] * len(jobs)

    def run(i, fn):
        try:
            vals[i] = fn()
        except Exception as ex:
            vals[i] = f"Fehler: {type(ex).__name__}"

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(run, i, fn)
                for i, (_, fn) in enumerate(jobs)]
        for f in futs:
            f.result()
    pairs = [("Benutzername", "@" + q)]
    for i, (name, _) in enumerate(jobs):
        pairs.append((name, vals[i]))
    pairs.append(("Hinweis", "nur oeffentliche Daten - kein Login, keine Tokens"))
    return pairs


# ---------------------------------------------------------------- Splash/Matrix
GLYPHS = "0123456789ABCDEF#$%&*<>/\\|+=:."


class MatrixRain:
    """Canvas-Digital-Rain fuer Splash und Matrix-Fenster (Spectre-Farben)."""

    def __init__(self, canvas, width, height, cols=36, cell=14, tail=9):
        self.cv = canvas
        self.w = width
        self.h = height
        self.cell = cell
        self.tail = tail
        step = width / max(4, cols)
        self.x = [int(i * step + step / 2) for i in range(cols)]
        self.y = [random.uniform(-height, height) for _ in range(cols)]
        self.sp = [random.uniform(3.5, 10.5) for _ in range(cols)]
        self.items = []
        for ci in range(cols):
            row = [canvas.create_text(self.x[ci], -60, text="",
                                      font=("Consolas", 9, "bold"),
                                      fill="#310000")
                   for _ in range(tail)]
            self.items.append(row)

    def step(self):
        h, cell, tail = self.h, self.cell, self.tail
        for ci in range(len(self.items)):
            self.y[ci] += self.sp[ci]
            if self.y[ci] - tail * cell > h:
                self.y[ci] = random.uniform(-tail * cell, -8)
                self.sp[ci] = random.uniform(3.5, 10.5)
            head = self.y[ci]
            for ti in range(tail):
                yy = head - ti * cell
                it = self.items[ci][ti]
                if yy < -cell or yy > h + cell:
                    self.cv.itemconfigure(it, text="")
                    continue
                if ti == 0:
                    fill = "#5ee9ff"   # Koepfe: eis-cyan
                elif ti < 3:
                    fill = "#e6e8ef"   # frische Spur: silber
                elif ti < 6:
                    fill = "#8a8f9c"
                else:
                    fill = "#3a3d45"
                if random.random() < 0.08:
                    fill = "#ffffff"  # seltener Glyphen-Blitz
                self.cv.itemconfigure(it, text=random.choice(GLYPHS), fill=fill)
                self.cv.coords(it, self.x[ci], yy)


class Splash(tk.Tk):
    """Startup-Splash: Matrix-Regen, Logo, Fortschritt (Spectre-Look)."""

    def __init__(self, on_done=None):
        super().__init__()
        self.on_done = on_done
        self.done = False
        self.title("SPECTRE Splash")  # unsichtbar (rahmenlos), nur zum Auffinden
        self.overrideredirect(True)
        self.configure(bg="#07070a")
        w, h = 560, 340
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
        self.canvas = tk.Canvas(self, width=w, height=h, bg="#07070a",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Regen (unten), Warntape darueber, Logo obenauf
        self.rain = MatrixRain(self.canvas, w, h, cols=36, cell=14, tail=9)
        for row_y in (0, h - 14):
            for i in range(0, w + 28, 28):
                col = "#b9bcc8" if (i // 28) % 2 == 0 else "#141414"
                self.canvas.create_rectangle(i, row_y, i + 28, row_y + 14,
                                             fill=col, width=0)
        cx = w // 2
        self.canvas.create_text(cx, 92, text="☠", font=("Segoe UI Emoji", 44),
                                fill="#ffffff")
        self.canvas.create_text(cx, 150, text="SPECTRE",
                                font=("Consolas", 30, "bold"), fill="#e6e8ef")
        self.canvas.create_text(cx, 180, text=f"SPECTRE EDITION  v{VER}",
                                font=("Consolas", 12, "bold"), fill="#5ee9ff")
        self.bar_bg = self.canvas.create_rectangle(
            cx - 190, 236, cx + 190, 254, fill="#17181d", outline="#3a3d45")
        self.bar_fill = self.canvas.create_rectangle(
            cx - 188, 238, cx - 188, 252, fill="#5ee9ff", width=0)
        self.pct_id = self.canvas.create_text(
            cx, 222, text="0%", font=("Consolas", 9, "bold"), fill="#e6e8ef")
        self.stage_id = self.canvas.create_text(
            cx, 274, text="", font=("Consolas", 9), fill="#9a9aa8")
        self.cx = cx
        self.stages = ["Kernmodule laden ...", "Lookup-Engines bereit ...",
                       "Matrix-Renderer ...", "Geo- + Social-Renderer ...",
                       "Nur-Lese-Modus erzwungen", "Systemstart ..."]
        self.stage = -1
        self.fast = os.environ.get("LOOKUP_GUI_FAST") == "1"
        self.total = 0.5 if self.fast else 2.3
        self.t0 = time.time()
        self._jobs = []
        self._anim()
        self._after(30, self._progress)
        # Sicherheits-Timeout: Fenster muss IMMER verschwinden
        self._after(int(self.total * 1000) + 7000, self._finish)

    def _after(self, ms, fn):
        """after-Job registrieren, damit _finish ihn absagen kann."""
        iid = self.after(ms, fn)
        self._jobs.append(iid)
        return iid

    def _anim(self):
        if self.done:
            return
        try:
            self.rain.step()
        except tk.TclError:
            return
        self._after(32, self._anim)

    def _progress(self):
        if self.done:
            return
        try:
            el = time.time() - self.t0
            pct = min(1.0, el / self.total)
            x = self.cx - 188 + int(pct * 376)
            self.canvas.coords(self.bar_fill, self.cx - 188, 238, x, 252)
            self.canvas.itemconfigure(self.pct_id,
                                      text=f"{int(pct * 100)}%")
            st = min(len(self.stages) - 1, int(pct * len(self.stages)))
            if st != self.stage:
                self.stage = st
                self.canvas.itemconfigure(self.stage_id,
                                          text=self.stages[st])
            if pct >= 1.0:
                fl = self.canvas.create_rectangle(0, 0, 560, 340,
                                                  fill="#ffffff", width=0)
                self._after(80, self._finish)
                self._after(40, lambda: self.canvas.delete(fl))
                return
        except tk.TclError:
            return
        self._after(40, self._progress)

    def _finish(self):
        if self.done:
            return
        self.done = True
        # Wartende after-Jobs absagen -> kein "invalid command"-Muell
        for iid in self._jobs:
            try:
                self.after_cancel(iid)
            except Exception:
                pass
        self._jobs.clear()
        cb, self.on_done = self.on_done, None
        try:
            self.destroy()
        except tk.TclError:
            pass
        if cb:
            cb()


def open_matrix_window():
    """Eigenes Matrix-Live-Fenster - Klick oder Esc beendet."""
    win = tk.Toplevel()
    win.title("SPECTRE // Matrix Live")
    win.configure(bg="#07070a")
    w, h = 720, 420
    win.geometry(f"{w}x{h}+{(win.winfo_screenwidth() - w) // 2}"
                 f"+{(win.winfo_screenheight() - h) // 3}")
    cv = tk.Canvas(win, width=w, height=h, bg="#07070a", highlightthickness=0)
    cv.pack(fill="both", expand=True)
    rain = MatrixRain(cv, w, h, cols=46, cell=14, tail=11)
    cv.create_text(w // 2, h // 2, text="☠  LOOKUP TOOL  ☠",
                   font=("Consolas", 22, "bold"), fill="#ffd400")
    cv.create_text(12, h - 14, anchor="w", text="MATRIX LIVE - Klick / Esc = Ende",
                   font=("Consolas", 10, "bold"), fill="#ff5500")
    state = {"run": True}

    def tick():
        if not state["run"]:
            return
        try:
            rain.step()
        except tk.TclError:
            return
        win.after(32, tick)

    def stop(_event=None):
        if state["run"]:
            state["run"] = False
            win.destroy()

    win.bind("<Escape>", stop)
    win.bind("<Button-1>", stop)
    tick()


# ---------------------------------------------------------------- GUI
class App(tk.Tk):
    BG = "#0a0a0c"

    def __init__(self):
        super().__init__()
        self.title(f"SPECTRE // Lookup Tool v{VER}")
        self.geometry("830x600")
        self.minsize(680, 480)
        self.q = queue.Queue()
        try:
            self.configure(bg=self.BG)
        except tk.TclError:
            pass
        self._apply_style()

        # Warntape oben
        tape = tk.Frame(self, height=7, bg=self.BG)
        tape.pack(fill="x", padx=8, pady=(8, 0))
        for i in range(52):
            tk.Frame(tape, width=17, height=7,
                     bg=("#b9bcc8" if i % 2 == 0 else "#1e1e22")
                     ).pack(side="left")

        # Kopfzeile mit Skull + Live-Uhr
        head = tk.Frame(self, bg=self.BG)
        head.pack(fill="x", padx=8, pady=(5, 0))
        tk.Label(head, text="☠ SPECTRE // LOOKUP",
                 font=("Consolas", 14, "bold"), fg="#e6e8ef",
                 bg=self.BG).pack(side="left")
        tk.Label(head, text="NUR-LESE · oeffentliche Daten",
                 font=("Consolas", 9), fg="#5ee9ff",
                 bg=self.BG).pack(side="left", padx=12)
        self.clock = tk.Label(head, text="", font=("Consolas", 10, "bold"),
                              fg="#5ee9ff", bg=self.BG)
        self.clock.pack(side="right")
        self._tick_clock()

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        self.results = {}
        self.busy = False
        self.tabs = [
            ("IP", self._make_tab("IP-Adresse oder leer lassen (eigene IP)", "IP abfragen", self._run_ip)),
            ("E-Mail", self._make_tab("name@beispiel.de", "E-Mail prüfen", self._run_email)),
            ("Benutzername", self._make_tab("z.B. max_mustermann", "Plattformen prüfen", self._run_user)),
            ("Domain", self._make_tab("z.B. example.de", "Domain abfragen", self._run_domain)),
            ("Snapchat", self._make_tab("Snapchat-Username, z.B. khaby.lame", "Snapchat prüfen", self._run_snap)),
            ("Account", self._make_tab("Benutzername für 9 Plattformen", "Accounts prüfen", self._run_acct)),
        ]

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Button(bar, text="Kopieren", command=self._copy).pack(side="left")
        ttk.Button(bar, text="Speichern ...", command=self._save).pack(side="left", padx=6)
        ttk.Button(bar, text="Leeren", command=self._clear).pack(side="left")
        ttk.Button(bar, text="☠ MATRIX", style="Hazard.TButton",
                   command=open_matrix_window).pack(side="left", padx=(14, 0))
        self.status = ttk.Label(bar, text="Bereit.")
        self.status.pack(side="right")

        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _apply_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=self.BG, foreground="#e8e8f0",
                     fieldbackground="#14151a", bordercolor="#2c2e35",
                     lightcolor="#2c2e35", darkcolor="#2c2e35",
                     troughcolor="#14151a", arrowcolor="#c9cdd9")
        st.configure("TNotebook", background=self.BG, borderwidth=0)
        st.configure("TNotebook.Tab", background="#17181d", foreground="#c9cdd9",
                     padding=(14, 6), font=("Consolas", 10, "bold"))
        st.map("TNotebook.Tab",
               background=[("selected", "#0f6f7d")],
               foreground=[("selected", "#ffffff")])
        st.configure("TFrame", background=self.BG)
        st.configure("TButton", background="#1b1c22", foreground="#c9cdd9",
                     focuscolor="#2c2e35", padding=(10, 5),
                     font=("Consolas", 9, "bold"))
        st.map("TButton",
               background=[("active", "#0f6f7d"), ("pressed", "#5ee9ff")],
               foreground=[("active", "#ffffff")])
        st.configure("Hazard.TButton", background="#0f6f7d",
                     foreground="#ffffff", padding=(10, 5),
                     font=("Consolas", 9, "bold"))
        st.map("Hazard.TButton",
               background=[("active", "#12899b"), ("pressed", "#5ee9ff")],
               foreground=[("pressed", "#000000")])
        st.configure("TLabel", background=self.BG, foreground="#e8e8f0")
        st.configure("TEntry", fieldbackground="#14151a", foreground="#e8e8f0",
                     insertcolor="#5ee9ff", bordercolor="#2c2e35",
                     lightcolor="#2c2e35", darkcolor="#2c2e35")
        st.configure("Vertical.TScrollbar", background="#1b1c22",
                     troughcolor="#14151a", arrowcolor="#c9cdd9",
                     bordercolor=self.BG)

    def _tick_clock(self):
        try:
            self.clock.configure(text=time.strftime("%H:%M:%S"))
        except tk.TclError:
            return
        self.after(1000, self._tick_clock)

    def _make_tab(self, hint, btn_text, runner):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text=" ... ")
        entry_row = ttk.Frame(f)
        entry_row.pack(fill="x", padx=8, pady=8)
        var = tk.StringVar()
        e = ttk.Entry(entry_row, textvariable=var)
        e.pack(side="left", fill="x", expand=True)
        b = ttk.Button(entry_row, text=btn_text, command=lambda: runner(var))
        b.pack(side="left", padx=(6, 0))
        e.bind("<Return>", lambda ev: runner(var))
        txt_frame = ttk.Frame(f)
        txt_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        txt = tk.Text(txt_frame, wrap="word", state="disabled", font=("Consolas", 10),
                      bg="#111216", fg="#d9dbe4", insertbackground="#5ee9ff",
                      selectbackground="#0f6f7d", relief="flat", padx=8, pady=8)
        sb = ttk.Scrollbar(txt_frame, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        # Tab-Label korrekt setzen
        self.results[id(f)] = txt
        return f, txt, var

    # -- Threads ---------------------------------------------------------
    def _start(self, txt_widget, label, fn, *args):
        if self.busy:
            messagebox.showinfo("Bitte warten", "Es läuft bereits eine Abfrage.")
            return
        self.busy = True
        self.status.configure(text=label + " ...")
        self._set(txt_widget, f"Läuft: {label} ... bitte warten\n")

        def work():
            try:
                out = fn(*args)
                text = out if isinstance(out, str) else fmt(out)
                self.q.put(("ok", txt_widget, text))
            except Exception as ex:
                self.q.put(("err", txt_widget, str(ex)))

        threading.Thread(target=work, daemon=True).start()

    def _set(self, txt, text):
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", text)
        txt.configure(state="disabled")

    def _append(self, txt, text):
        txt.configure(state="normal")
        txt.insert("end", text)
        txt.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                kind, txt, text = self.q.get_nowait()
                if kind == "ok":
                    self._set(txt, text + "\n")
                    self.status.configure(text="Fertig.")
                else:
                    self._set(txt, "FEHLER: " + text + "\n")
                    self.status.configure(text="Fehler.")
                self.busy = False
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # -- Runners ---------------------------------------------------------
    def _run_ip(self, var):
        tab, txt, _ = self._current()
        self._start(txt, "IP-Abfrage", lookup_ip, var.get())

    def _run_email(self, var):
        tab, txt, _ = self._current()
        self._start(txt, "E-Mail-Prüfung", lookup_email, var.get())

    def _run_user(self, var):
        tab, txt, _ = self._current()
        self._start(txt, "Benutzername-Prüfung", lookup_username, var.get())

    def _run_domain(self, var):
        tab, txt, _ = self._current()
        self._start(txt, "Domain-Abfrage", lookup_domain, var.get())

    def _run_snap(self, var):
        tab, txt, _ = self._current()
        self._start(txt, "Snapchat-Profil", lookup_snapchat, var.get())

    def _run_acct(self, var):
        tab, txt, _ = self._current()
        self._start(txt, "Account-View", lookup_account_view, var.get())

    def _current(self):
        sel = self.nb.select()
        for child in self.nb.winfo_children():
            if str(child) == sel:
                return child, self.results[id(child)], None
        return None, None, None

    def _copy(self):
        _, txt, _ = self._current()
        if txt:
            self.clipboard_clear()
            self.clipboard_append(txt.get("1.0", "end").strip())
            self.status.configure(text="In Zwischenablage kopiert.")

    def _save(self):
        _, txt, _ = self._current()
        if not txt:
            return
        content = txt.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("Leer", "Keine Ergebnisse zum Speichern.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            initialfile="lookup_ergebnis.txt",
                                            filetypes=[("Textdateien", "*.txt"), ("Alle Dateien", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.status.configure(text=f"Gespeichert: {path}")

    def _clear(self):
        _, txt, _ = self._current()
        if txt:
            self._set(txt, "")


def main():
    def open_app():
        app = App()
        # Tab-Labels nachträglich korrekt setzen (Platzhalter aus _make_tab)
        for i, (label, (frame, txt, var)) in enumerate(app.tabs):
            app.nb.tab(frame, text=" " + label + " ")
        if os.environ.get("LOOKUP_GUI_AUTOCLOSE") == "1":
            app.after(900, app.destroy)
        app.mainloop()

    splash = Splash(on_done=open_app)
    splash.mainloop()  # endet, sobald der Splash sich zerstoert hat
    return 0


if __name__ == "__main__":
    sys.exit(main())
