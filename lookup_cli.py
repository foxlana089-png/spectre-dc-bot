# -*- coding: utf-8 -*-
"""
SPECTRE v2.7 - Terminal-Version im Silber/Schwarz-Look (Vorbild MARTIN)
37 Abfragen, inkl. IP-Geo-Karte (Weltkarte + Marker + Distanz
+ VPN/Rechenzentrum-Erkennung), Snapchat-Profil, Account-View
(9 Plattformen parallel), Hacker-News/Steam/Repo/Paket/Wayback/
Bedrohungs/Kurs/NASA/Feiertage, Discord-Bot (!hilfe) und Webhook-Nachricht.
Die Lookups bleiben strikt Nur-Lese (nur oeffentliche Daten); Nachrichten
gehen mit eigenem Bot-Token ausschliesslich in den eigenen Discord-Server.
Kern-Funktionen aus lookup_tool.py.
"""
import hashlib
import json
import os
import random
import re
import socket
import ssl
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lookup_tool as core

# ---------------------------------------------------------------- Output
def enable_ansi():
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        k32.GetConsoleMode(h, ctypes.byref(mode))
        k32.SetConsoleMode(h, mode.value | 0x0004)
        os.system("")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

enable_ansi()

R, BOLD, DIM = "\x1b[0m", "\x1b[1m", "\x1b[2m"
RED, GREEN, YELLOW = "\x1b[91m", "\x1b[1;96m", "\x1b[1;96m"
BLUE, MAGENTA, CYAN = "\x1b[94m", "\x1b[95m", "\x1b[96m"
WHITE, GRAY, SILVER = "\x1b[97m", "\x1b[90m", "\x1b[37m"

# SPECTRE-Palette (Silber/Schwarz, EIS-CYAN als einziger Akzent):
# Cyan = Aktiv/Erfolg/Marken, Weiss/Silber = Daten, Grau = neutral,
# Rot = echte Fehler. Reine Optik - Funktionen bleiben strikt Nur-Lese.
WARN = "\x1b[1;96m"     # Akzent: Titel/Labels/Prozent
FIRE = "\x1b[1;96m"     # Akzent: Progress/Marker/Pfeile
BLOOD = "\x1b[1;97m"    # Silver-Weiss fuer Deko (Blloecke/Skulls)
ACID = "\x1b[1;97m"     # Werte "gefunden" (Bold-Weiss)

GRADIENT = ["\x1b[1;97m", "\x1b[37m", "\x1b[1;90m", "\x1b[37m", "\x1b[1;97m"]

BANNER = [
    r"    ☠ ☠ ☠ ☠ ☠ ☠ ☠ ☠ ☠ ☠ ☠ ☠",
    r"   ██████╗██████╗ ███████╗ ██████╗████████╗██████╗ ███████╗",
    r"   ██╔════╝██╔══██╗██╔════╝██╔════╝╚══██╔══╝██╔══██╗██╔════╝",
    r"   ███████╗██████╔╝█████╗  ██║        ██║   ██████╔╝█████╗  ",
    r"   ╚════██║██╔═══╝ ██╔══╝  ██║        ██║   ██╔══██║██╔══╝  ",
    r"   ████████║██║     ███████╗╚██████╗   ██║   ██║  ██║███████╗",
    r"   ╚══════╝╚═╝     ╚══════╝ ╚═════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝",
    r"  ▓▓ SPECTRE ░ NUR-LESE-MODUS ░ SPECTRE ▓▓",
]
BANNER2 = [
    r"   _  __          _                    _         ",
    r"  | |/ /___  ___ | | _____ _ __   ___| |__  _ _ ",
    r"  | ' // _ \/ _ \| |/ / _ \ '_ \ / _ \ '_ \| | | |".replace("??", "??"),
    r"  | . \  __/ (_) |   <  __/ |_) |  __/ |_) | |_| |",
    r"  |_|\_\___|\___/|_|\_\___| .__/ \___|_.__/ \__, |",
    r"                          |_|               |___/ ",
]

VER = "2.7"

# Warntape + komplette Splash-Zeilen (Logo zwischen den Baendern)
TAPE_LINE = "  " + "██░░" * 14 + "██"
SPLASH_LINES = [TAPE_LINE] + BANNER + [TAPE_LINE]

# ---------------------------------------------------------------- Farb-Helfer
def c(text, color):
    return f"{color}{text}{R}"


def slow_print(text, delay=0.012):
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")


def gradient_print(lines):
    for i, line in enumerate(lines):
        print(c(line, GRADIENT[i % len(GRADIENT)]))
        time.sleep(0.05)


# ---------------------------------------------------------------- Spinner/Progress
class Spinner:
    FRAMES = ["|", "/", "-", "\\"]
    GLYPHS = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#$%&*<>/\\"

    def __init__(self, text="Abfrage"):
        self.text = text
        self.running = False
        self.thread = None

    def _scramble(self, seed):
        """Text wirkt beim Abfragen wie beim Entschluesseln."""
        rnd = random.Random(seed)
        out = []
        for ch in self.text:
            if ch == " " or not ch.isascii() or rnd.random() >= 0.55:
                out.append(ch)
            else:
                out.append(rnd.choice(self.GLYPHS))
        return "".join(out)

    def _loop(self):
        i = 0
        while self.running:
            fr = self.FRAMES[i % 4]
            col = [CYAN, WHITE, SILVER, CYAN][i % 4]
            body = self._scramble(i)
            sys.stdout.write(
                f"\r   {col}{fr}{R} {WARN}{body}{R} {DIM}...{R}   ")
            sys.stdout.flush()
            i += 1
            time.sleep(0.11)

    def __enter__(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
        sys.stdout.write("\r" + " " * 70 + "\r")
        sys.stdout.flush()


def progress(label, i, n, width=22):
    filled = int(width * i / max(n, 1))
    bar = c("█" * filled, FIRE) + c("░" * (width - filled), GRAY)
    sys.stdout.write(f"\r   [{bar}] {DIM}{label} {i}/{n}{R}   ")
    sys.stdout.flush()


def progress_done():
    sys.stdout.write("\r" + " " * 70 + "\r")
    sys.stdout.flush()


def splash_progress(duration=2.1):
    """Terminale Variante des GUI-Splash: Stage + Spinner + Balken + %."""
    stages = [
        "Kernmodule laden ...",
        "Lookup-Engines bereit ...",
        "Matrix-Renderer gestartet ...",
        "Geo- + Social-Renderer ...",
        "Nur-Lese-Modus erzwungen ...",
        "SPECTRE-Protokoll aktiv ...",
    ]
    width = 24
    spin = "|/-\\"
    t0 = time.time()
    i = 0
    while True:
        p = min(1.0, (time.time() - t0) / duration)
        i += 1
        filled = int(width * p)
        st_idx = min(len(stages) - 1, int(p * len(stages)))
        bar = c("█" * filled, FIRE) + c("░" * (width - filled), GRAY)
        stage_col = GRADIENT[st_idx % len(GRADIENT)]
        line = (f"   {CYAN}{spin[i % 4]}{R} "
                f"{stage_col}{stages[st_idx]:<30}{R} "
                f"{WHITE}[{bar}]{R} {BOLD}{WARN}{int(p * 100):>3}%{R}")
        sys.stdout.write("\r\x1b[2K" + line)
        sys.stdout.flush()
        if p >= 1.0:
            break
        time.sleep(0.033)
    sys.stdout.write("\n")
    sys.stdout.flush()


def hazard_flash():
    """Blitz-Frames: weiss -> hell -> eis-cyan -> leer (Spectre-Blitz)."""
    for bg in (107, 47, 106):
        block = f"\x1b[1;{bg}m" + " " * 76 + "\x1b[0m\n"
        sys.stdout.write("\x1b[H" + block * 20 + "\x1b[J")
        sys.stdout.flush()
        time.sleep(0.055)
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()
    time.sleep(0.06)


# ---------------------------------------------------------------- Layout
def vis_len(s):
    """Sichtbare Laenge ohne ANSI-Farbcodes."""
    return len(re.sub(r"\x1b\[[0-9;]*m", "", s))


def header(title):
    """Titel-Linie zeichnet sich Strich fuer Strich selbst (mit Skull)."""
    n = max(2, 38 - len(title))
    print()
    sys.stdout.write(f"  {SILVER}╭─ {WHITE}☠ {BOLD}{WARN}{title}{R}{SILVER} ")
    sys.stdout.flush()
    step = max(1, n // 6)
    drawn = 0
    while drawn < n:
        k = min(step, n - drawn)
        sys.stdout.write("─" * k)
        sys.stdout.flush()
        drawn += k
        time.sleep(0.02)
    sys.stdout.write(f"╮{R}\n")
    sys.stdout.flush()


def _scramble_text(text, seed):
    """ASCII als Krammel, ANSI/Unicode bleiben (Breite bleibt stabil)."""
    rnd = random.Random(seed)
    pool = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#$%&*<>/\\"
    out, i = [], 0
    while i < len(text):
        if text[i] == "\x1b":
            m = re.match(r"\x1b\[[0-9;]*m", text[i:])
            if m:
                out.append(m.group(0))
                i += len(m.group(0))
                continue
        ch = text[i]
        if ch == " " or not ch.isascii() or rnd.random() >= 0.6:
            out.append(ch)
        else:
            out.append(rnd.choice(pool))
        i += 1
    return "".join(out)


def _emit_row(line, seed):
    """Decryption-Look: Zeile kurz als Krammel, dann in derselben echt."""
    plain = re.sub(r"\x1b\[[0-9;]*m", "", line)
    if not re.search(r"[A-Za-z0-9]", plain):
        print(line)
        return
    sys.stdout.write(_scramble_text(line, seed) + "\n")
    sys.stdout.flush()
    time.sleep(0.03)
    sys.stdout.write("\x1b[1A\x1b[2K" + line + "\n")
    sys.stdout.flush()


def show_results(pairs, width=54, decrypt=True):
    pairs = [(k, v) for k, v in pairs if v is not None]
    if not pairs:
        print(f"   {GRAY}(keine Ergebnisse){R}")
        return
    w = max(vis_len(str(k)) for k, _ in pairs) + 2
    inner = w + width + 4
    lines = [f"   {RED}╭{'─' * inner}╮{R}"]
    for k, v in pairs:
        v = str(v)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", v)
        if vis_len(v) <= width:
            # Kurzer Wert: Original mit Farben anzeigen
            label = str(k)
            pad = width - vis_len(v)
            lines.append(
                f"   {RED}│{R} {WARN}{label}{' ' * max(0, w - vis_len(label))}{R}"
                f" {ACID}{v}{' ' * pad}{R} {RED}│{R}")
            continue
        # Langer Wert: an sichtbarer Breite umbrechen (Farben entfallen)
        chunks = [plain[i:i + width] for i in range(0, len(plain), width)] or [""]
        first = True
        for chunk in chunks:
            label = str(k) if first else ""
            pad = width - vis_len(chunk)
            lines.append(
                f"   {RED}│{R} {WARN}{label.ljust(vis_len(label) + 0)}{R}"
                f"{' ' * max(0, w - vis_len(label))}{ACID}{chunk}{' ' * pad}"
                f"{R} {RED}│{R}")
            first = False
    lines.append(f"   {RED}╰{'─' * inner}╯{R}")
    if decrypt:
        for idx, ln in enumerate(lines):
            _emit_row(ln, idx * 7 + 3)
    else:
        for ln in lines:
            print(ln)


def ok(msg):
    print(f"   {GREEN}✔{R} {msg}")


def err(msg):
    print(f"   {RED}✘ {msg}{R}")


def info(msg):
    print(f"   {CYAN}i{R} {GRAY}{msg}{R}")


def hazard_bar(width=66):
    """Spectre-Tape: silbergeklaeterter Trennbalken (Optik)."""
    out = []
    for i in range(width):
        if i % 4 < 2:
            out.append(f"{SILVER}█")
        else:
            out.append(f"{GRAY}░")
    return "".join(out) + R


MENU_ITEMS = [
    ("1",  "IP & Geo-Karte"),
    ("2",  "E-Mail (erweitert)"),
    ("3",  "Benutzername (16 Seiten)"),
    ("4",  "DNS / Domain"),
    ("5",  "Telefonnummer"),
    ("6",  "MAC-Adresse"),
    ("7",  "Website-Sicherheit"),
    ("8",  "SSL-Zertifikat"),
    ("9",  "Port-Check"),
    ("10", "IBAN-Pruefung"),
    ("11", "Krypto-Kurse"),
    ("12", "User-Agent"),
    ("13", "Discord-Invite"),
    ("14", "GitHub-Profil"),
    ("15", "E-Mail-Header-Analyse"),
    ("16", "Meine IP (Link)"),
    ("17", "Discord-Webhook"),
    ("18", "Discord-Status"),
    ("19", "Wetter"),
    ("20", "Wechselkurs"),
    ("21", "Wikipedia"),
    ("22", "YouTube-Info"),
    ("23", "IP-Netz (RDAP)"),
    ("24", "Route (Traceroute)"),
    ("25", "Netzwerk (lokal)"),
    ("26", "Snapchat-Profil"),
    ("27", "Account-View (Social)"),
    ("28", "Hacker-News"),
    ("29", "Steam-Check"),
    ("30", "GitHub-Repo"),
    ("31", "Paket npm/PyPI"),
    ("32", "Wayback-Archiv"),
    ("33", "Bedrohungs-Check"),
    ("34", "Aktienkurs"),
    ("35", "NASA-Bild des Tages"),
    ("36", "Feiertage"),
    ("37", "Discord senden"),
]

DESC = {
    "1":  "IP -> Land, Stadt, Koordinaten + Weltkarte mit Zielmarke, Distanz zu dir, VPN/Rechenzentrum-Erkennung",
    "2":  "MX, SPF, DKIM, DMARC, Gravatar, Wegwerf-Check, Leck-Link",
    "3":  "Prueft einen Namen auf 16 Plattformen mit Fortschrittsbalken",
    "4":  "Alle DNS-Typen (A/AAAA/MX/NS/TXT/CNAME/SOA/CAA) + WHOIS",
    "5":  "E.164-Format, Land, Mobil-/Festnetz-Ratgeber",
    "6":  "Hersteller ueber OUI-Datenbank, Multicast-/Lokal-Bits",
    "7":  "HTTPS, HSTS, CSP, X-Frame, Server-Leaks + Sicherheits-Score",
    "8":  "Zertifikat-Aussteller, Gueltigkeit, SAN, Restlaufzeit",
    "9":  "20 gängige Ports, Ping und rDNS vom Ziel-Host",
    "10": "Pruefziffer (MOD-97), Laenge, Format, Land",
    "11": "Top-Coins in USD/EUR mit 24h-Änderung (CoinGecko)",
    "12": "Browser, Betriebssystem, Geraet aus einem UA-String",
    "13": "Servername, Mitglieder, Inviter, Verifizierung (offizielle API)",
    "14": "Profil: Bio, Repos, Follower, letztes Update (GitHub-API)",
    "15": "Header einfuegen -> Ursprung-IP, Land/ISP, Hop-Kette, SPF/DKIM/DMARC, Client",
    "16": "Oeffentliche eigene IP + Klick-Link oeffnet ipinfo.io (IP, Stadt, ISP)",
    "17": "Eigene Discord-Webhook-URL pruefen: Name, Server/Kanal-ID (nur lesen)",
    "18": "Offizieller Discord-Serverstatus: Ausfaelle, gewartete Komponenten",
    "19": "Stadt eingeben -> Temperatur, Wind, Luftfeuchte, Zustand (open-meteo)",
    "20": "Waehrungsumrechnung, z.B. '100 USD EUR' (open.er-api, kostenlos)",
    "21": "Artikel suchen -> Zusammenfassung + Link (de.wikipedia.org)",
    "22": "YouTube-Link/ID -> Titel + Kanal (oEmbed, kein Login noetig)",
    "23": "Welches Netz gehoert der IP? Netname, Bereich, Land, Status (RDAP)",
    "24": "Route zum Ziel mit Hops und Laufzeiten (Windows tracert)",
    "25": "Eigene IPv4, Gateway, DNS-Server und.hostname (ipconfig-Auswertung)",
    "26": "Oeffentliches Snapchat-Add-Profil: Anzeigename, Beschreibung, "
          "Vorschaubild, Profil-URL (kein Login, kein Steal)",
    "27": "Benutzername gegen 9 Plattformen parallel: GitHub, Snapchat, "
          "Telegram, Twitch, SoundCloud, Steam, Reddit, X, Instagram",
    "28": "Top-Storys mit Punkten und Links (Hacker-News, offen und keyless)",
    "29": "Spiel ueber Store-Suche: Preis, Rabatt, Metacritic, Release (Steam)",
    "30": "'owner/repo' -> Stars, Forks, Issues, Sprache, Lizenz (GitHub-API)",
    "31": "Paket-Name -> Version, Lizenz, Veroeffentlichung (PyPI/npm, keyless)",
    "32": "URL -> aeltester bekannter Snapshot der Wayback Machine (archive.org)",
    "33": "Domain gegen OpenPhish-Phishing-Feed + urlscan.io-Scans (keyless)",
    "34": "Aktie eingeben, z.B. 'aapl' oder 'sap.de' -> Kurs + Vortag (Yahoo)",
    "35": "Astronomie-Bild des Tages mit Titel und Erklaerung (NASA DEMO_KEY)",
    "36": "Laendernummer, z.B. DE/AT/CH -> kommende Feiertage (date.nager.at)",
    "37": "Eigene Discord-Webhook-URL + Text -> einmal oder N-mal senden (max 1000)",
}


def show_menu():
    rows = (len(MENU_ITEMS) + 1) // 2
    left = MENU_ITEMS[:rows]
    right = MENU_ITEMS[rows:]
    print()
    title = (f"   {GRAY}███{R} {BOLD}SPECTRE // LOOKUP CONTROL{R} "
             f"{GRAY}|{R} {SILVER}v{VER}{R} {GRAY}|{R} "
             f"{CYAN}{time.strftime('%H:%M:%S')}{R} {GRAY}|{R} "
             f"{DIM}NUR-LESE{R}")
    plain = re.sub(r"\x1b\[[0-9;]*m", "", title)
    title += " " * max(1, 68 - len(plain)) + f"{WHITE}☠{R}"
    print(title)
    print(f"   {hazard_bar(66)}")
    for i in range(rows):
        ln, lt = left[i] if i < len(left) else ("", "")
        rn, rt = right[i] if i < len(right) else ("", "")
        lplain = f"  [{ln:>2}] {lt:<24}" if ln else ""
        l = (f"  {GRAY}[{R}{CYAN}{ln:>2}{R}{GRAY}]{R} "
             f"{WHITE}{lt:<24}{R}") if ln else ""
        rplain = f"  [{rn:>2}] {rt:<24}" if rn else ""
        r = (f"  {GRAY}[{R}{CYAN}{rn:>2}{R}{GRAY}]{R} "
             f"{WHITE}{rt:<24}{R}") if rn else ""
        pad = " " * max(1, 34 - len(lplain))
        print(f"{l}{pad}{GRAY}│{R} {r}")
    print(f"   {hazard_bar(66)}")
    print(f"  {RED} 0 {WHITE}Beenden{R}   {CYAN}b{R} {WHITE}Discord-Bot{R}   "
          f"{CYAN}m{R} {WHITE}Matrix-Live{R}   {GRAY}'info Nr.' = Beschreibung{R}")
    print()


def animate_exit():
    for i in range(21):
        progress("Abmeldung", i, 20, width=20)
        time.sleep(0.03)
    progress_done()
    print()
    user = os.environ.get("USERNAME", "User")
    for ch in f"LOGOUT {user} ...":
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(0.035)
    print()
    time.sleep(0.2)
    matrix_rain(0.7)
    print(f"\n   {BLOOD}{BOLD}☠ VERBINDUNG GETRENNT ☠{R}")
    print(f"   {GRAY}Lookup Tool v{VER} beendet.{R}\n")


# ================================================================ LOOKUPS
_LAST_GEO = None  # wird von lookup_ip_full fuer die Karte gefuellt

LAND_MAP = {
    0:  [(11, 24), (22, 32), (38, 40), (48, 52), (55, 57), (62, 66)],
    1:  [(3, 8), (8, 24), (22, 32), (38, 71)],
    2:  [(2, 8), (8, 25), (25, 32), (31, 33), (37, 71)],
    3:  [(0, 8), (9, 25), (26, 27), (34, 71)],
    4:  [(11, 24), (34, 65)],
    5:  [(11, 21), (34, 64)],
    6:  [(13, 21), (32, 60)],
    7:  [(15, 24), (32, 47), (50, 61)],
    8:  [(19, 26), (33, 46), (52, 61)],
    9:  [(20, 29), (33, 44), (56, 64)],
    10: [(20, 29), (33, 46), (58, 66)],
    11: [(22, 28), (32, 46), (58, 66)],
    12: [(21, 25), (32, 42), (58, 66), (70, 71)],
    13: [(21, 23), (58, 66), (69, 71)],
    14: [(21, 24)],
    15: [(23, 25), (56, 70)],
    16: [(0, 71)],
    17: [(0, 71)],
}
_WORLD = None


def _build_world():
    """72x18-Gitter (5 Grad lon x 10 Grad lat), Equirektangular."""
    global _WORLD
    if _WORLD is None:
        grid = [[" "] * 72 for _ in range(18)]
        for r, spans in LAND_MAP.items():
            for a, b in spans:
                for x in range(max(0, a), min(71, b) + 1):
                    grid[r][x] = "#"
        _WORLD = grid
    return _WORLD


def print_geo_map(geo):
    """Weltkarte im Terminal + Zielmarke."""
    lat, lon = float(geo["lat"]), float(geo["lon"])
    grid = [row[:] for row in _build_world()]
    mr = max(0, min(17, int((90 - lat) / 10)))
    mc = max(0, min(71, int((lon + 180) / 5)))
    grid[mr][mc] = "X"
    title = f"GEO-KARTE  {geo.get('ip', '')}  {lat:.2f}/{lon:.2f}"
    pad = max(2, 71 - len(title))
    print(f"   {RED}╭─ {WARN}{title}{R}{RED} {'─' * pad}╮{R}")
    colors = {" ": R, "#": GRAY, "X": f"{BLOOD}{BOLD}"}
    for row in grid:
        parts, cur, buf = [], None, ""
        for ch in row:
            if ch != cur:
                if cur is not None:
                    parts.append(colors[cur] + buf)
                cur, buf = ch, ch
            else:
                buf += ch
        parts.append(colors[cur] + buf)
        print(f"   {RED}│{R} {''.join(parts)} {RED}│{R}")
    print(f"   {RED}╰{'─' * 74}╯{R}")
    print(f"   {BLOOD}{BOLD}X{R} {DIM}= Zielmarke  {GRAY}# = Land"
          f"{R}  {DIM}Raster 5x10 Grad, Ozeane leer{R}")


def _haversine_km(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, asin, sqrt
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (sin(dlat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2)
    return 2 * 6371 * asin(sqrt(min(1.0, a)))


def _compass(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, atan2, degrees
    p1, p2 = radians(lat1), radians(lat2)
    dl = radians(lon2 - lon1)
    x = sin(dl) * cos(p2)
    y = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl)
    brng = (degrees(atan2(x, y)) + 360) % 360
    names = ["N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return names[int((brng + 11.25) // 22.5) % 16]


def _classify_conn(isp, org):
    """Heuristik: VPN, Rechenzentrum oder Privat-ISP (nur Anzeige)."""
    s = f"{isp or ''} {org or ''}".lower()
    if any(k in s for k in ("mullvad", "vpn", "proxy", "hidemyass",
                            "anchorfree", "tor project", "exitnode")):
        return c("VPN / PROXY - Standort evtl. gefaelscht", RED)
    if any(k in s for k in ("datacenter", "hosting", "cloud", "server",
                            "vps", "dedicated", "amazon", "google",
                            "microsoft", "azure", "ovh", "hetzner",
                            "digitalocean", "linode", "choopa", "leaseweb",
                            "contabo", "scaleway", "akamai", "cloudflare",
                            "fastly", "aliyun", "tencent", "oracle")):
        return c("Rechenzentrum / Hosting (kein Privat-ISP)", SILVER)
    return c("Wahrscheinlich privater ISP-Anschluss", GREEN)


def lookup_ip_full(query):
    global _LAST_GEO
    _LAST_GEO = None
    q = (query or "").strip()
    if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}:\d+$", q):
        q = q.split(":")[0]
    if q and re.match(
            r"^(?:10\.|127\.|192\.168\.|169\.254\.|0\."
            r"|172\.(?:1[6-9]|2\d|3[01])\.)", q):
        raise ValueError(
            f"{q} ist eine private/local IP - kein Geo-Datensatz (LAN)")
    if q.lower().startswith(("::1", "fc", "fd", "fe80")):
        raise ValueError("Private IPv6 - kein Geo-Datensatz (LAN)")
    d = core.http_json("https://ipwho.is/" + q)
    if not d.get("success", True):
        raise ValueError(d.get("message", "IP nicht gefunden"))
    conn = d.get("connection") or {}
    tz = d.get("timezone") or {}
    flag = d.get("flag") or {}
    cur = d.get("currency") or {}
    lat, lon = d.get("latitude"), d.get("longitude")
    ip = d.get("ip")
    try:
        rdns = socket.gethostbyaddr(ip)[0] if ip else "-"
    except Exception:
        rdns = "-"
    # Distanz zum eigenen Standort (eigene IP via ipwho.is, kostenlos)
    dist_str = None
    if lat is not None and lon is not None:
        try:
            own = core.http_json("https://ipwho.is/") if q else d
            if own.get("success", True) and own.get("latitude") is not None:
                km = _haversine_km(own["latitude"], own["longitude"], lat, lon)
                dirn = _compass(own["latitude"], own["longitude"], lat, lon)
                if own.get("ip") == ip:
                    dist_str = "0 km - das ist deine eigene IP"
                else:
                    km_s = f"{km:,.0f}".replace(",", ".")
                    dist_str = f"{km_s} km Richtung {dirn}"
        except Exception:
            dist_str = None
    lines = [
        ("IP-Adresse", ip),
        ("Typ", d.get("type")),
        ("Flagge", flag.get("emoji") if flag.get("emoji") else None),
        ("Land", f'{d.get("country")} ({d.get("country_code")})'),
        ("Kontinent", d.get("continent")),
        ("Region", d.get("region")),
        ("Stadt", f'{d.get("city")} {d.get("postal")}'),
        ("Koordinaten", f"{lat}, {lon}"),
        ("Zeitzone", tz.get("id") if isinstance(tz, dict) else tz),
        ("Waehrung",
         (f'{cur.get("name") or "-"} ({cur.get("code") or "-"}) '
          f'{cur.get("symbol") or ""}').strip() if cur else None),
        ("ISP / Anbieter", conn.get("isp")),
        ("Organisation", conn.get("org")),
        ("ASN", conn.get("asn")),
        ("rDNS (Reverse-DNS)", rdns),
        ("Anschluss-Typ", _classify_conn(conn.get("isp"), conn.get("org"))),
        ("Distanz zu dir", dist_str),
    ]
    if lat is not None and lon is not None:
        _LAST_GEO = {"lat": float(lat), "lon": float(lon),
                     "ip": ip, "city": d.get("city")}
    return lines


def _doh(name, qtype_names):
    url = ("https://cloudflare-dns.com/dns-query?name="
           + urllib.parse_quote(name) + "&type=" + qtype_names)
    req = urllib.request.Request(url, headers={**core.UA,
                                               "Accept": "application/dns-json"})
    with urllib.request.urlopen(req, timeout=core.TIMEOUT) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return [str(a.get("data", "")).rstrip(".")
            for a in (d.get("Answer") or [])]


import urllib.parse as _up
urllib.parse_quote = _up.quote

DNS_TYPES = [
    ("A", "A"), ("AAAA", "AAAA"), ("MX", "MX"), ("NS", "NS"),
    ("TXT", "TXT"), ("CNAME", "CNAME"), ("SOA", "SOA"), ("CAA", "CAA"),
]


def lookup_dns_full(domain):
    domain = domain.strip().lower().rstrip(".")
    if not re.match(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$", domain):
        raise ValueError("Ungueltige Domain")
    out = [("Domain", domain)]
    for label, qtype in DNS_TYPES:
        try:
            res = _doh(domain, qtype)
            # Werte kuerzen
            joined = ", ".join(res[:4])
            if len(res) > 4:
                joined += f" (+{len(res) - 4} weitere)"
            out.append((f"DNS {label}", joined or "keine Eintraege"))
        except Exception as e:
            out.append((f"DNS {label}", f"Fehler ({type(e).__name__})"))
    # WHOIS/RDAP
    try:
        d = core.http_json("https://rdap.org/domain/" + domain)
        out.append(("Registrar", core._rdap_registrar(d)))
        events = {e.get("eventAction"): e.get("eventDate")
                  for e in d.get("events", [])}
        out.append(("Registriert", events.get("registration", "-")))
        out.append(("Laeuft ab", events.get("expiration", "-")))
        out.append(("Status", ", ".join(d.get("status", [])[:5]) or "-"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            out.append(("WHOIS/RDAP", "nicht registriert (404)"))
        else:
            out.append(("WHOIS/RDAP", f"HTTP {e.code}"))
    except Exception as e:
        out.append(("WHOIS/RDAP", f"Fehler ({type(e).__name__})"))
    return out


def lookup_email_full(query):
    """Erweiterte E-Mail-Pruefung inkl. oeffentlich ableitbarer Fakten."""
    email = query.strip().lower()
    out = []
    if not core.EMAIL_RE.match(email):
        return [("Syntax", "FEHLER - ungueltiges Format")]
    out.append(("Syntax", "OK"))
    domain = email.split("@")[1]
    out.append(("Domain", domain))
    out.append(("Wegwerf-Domain", "JA" if domain in core.DISPOSABLE else "Nein"))
    try:
        socket.getaddrinfo(domain, 80)
        out.append(("Domain erreichbar", "Ja"))
    except Exception:
        out.append(("Domain erreichbar", "NEIN - existiert nicht"))
        return out
    # Mail-Infrastruktur
    mx = []
    try:
        mx = core.dns_query(domain, 15)
        out.append(("MX (Mail-Server)", ", ".join(mx[:3]) if mx else "KEINE Eintraege"))
    except Exception as e:
        out.append(("MX", f"Fehler ({e})"))
    for label, q in (("SPF", 16),):
        try:
            txts = core.dns_query(domain, q)
            spf = [t for t in txts if t.lower().startswith("v=spf1")]
            out.append((label, (spf[0][:90] if spf else "kein SPF - Mail kann leicht gefaelscht werden")))
        except Exception:
            out.append((label, "Abfrage fehlgeschlagen"))
    # DMARC
    try:
        dmarc = core.dns_query("_dmarc." + domain, 16)
        d0 = [t for t in dmarc if t.lower().startswith("v=dmarc1")]
        out.append(("DMARC", d0[0][:90] if d0[0:1] else "kein DMARC-Eintrag"))
    except Exception:
        out.append(("DMARC", "Abfrage fehlgeschlagen"))
    # DKIM (haeufige Selector) - parallel via DoH, sonst zu langsam
    dkim_found = []
    selectors = ("default", "google", "selector1", "selector2", "k1",
                 "mail", "s1", "s2")

    def _dkim(sel):
        try:
            r = _doh(f"{sel}._domainkey.{domain}", "TXT")
            if any("p=" in t for t in r):
                return sel
        except Exception:
            pass
        return None

    threads, results = [], []
    for sel in selectors:
        t = threading.Thread(target=lambda s=sel: results.append(_dkim(s)),
                             daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=6)
    dkim_found = [s for s in results if s]
    out.append(("DKIM-Selector", ", ".join(sorted(set(dkim_found))) if dkim_found
                else "keiner der 8 gängigen Selector gefunden"))
    # Gravatar (oeffentliches Profil-Bild zum E-Mail-Hash)
    h = hashlib.md5(email.encode()).hexdigest()
    grav = [("kein Profil", "-")]
    try:
        req = urllib.request.Request(
            f"https://www.gravatar.com/{h}.json?d=404", headers=core.UA)
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        entry = (d.get("entry") or [d])[0]
        name = entry.get("displayName") or entry.get("preferredUsername") or "?"
        loc = entry.get("currentLocation") or "-"
        urls = ", ".join(u.get("url", "") for u in (entry.get("urls") or [])[:3])
        out.append(("Gravatar-Profil", f"{name} | Ort: {loc}" + (f" | Links: {urls}" if urls else "")))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            out.append(("Gravatar-Profil", "kein öffentliches Profil zu diesem Hash"))
        else:
            out.append(("Gravatar-Profil", f"HTTP {e.code}"))
    except Exception as e:
        out.append(("Gravatar-Profil", f"Fehler ({type(e).__name__})"))
    # Hosting-Anbieter & Standort der Mail-Server erkennen
    if mx:
        mx_hosts = [e.split()[-1].lower().rstrip(".") for e in mx if e.split()]
        blob = " ".join(mx_hosts) + " " + domain
        rules = [
            ("google|gmail", "Google Workspace / Gmail"),
            ("microsoft|outlook", "Microsoft 365 / Outlook"),
            ("yahoo", "Yahoo Mail"), ("proton", "Proton Mail"),
            ("tuta|tutanota", "Tutanota"),
            ("ionos|1und1|ui-dns|u1-|mx\\.ha-", "IONOS / 1&1"),
            ("godaddy", "GoDaddy"), ("zoho", "Zoho Mail"),
            ("fastmail", "Fastmail"), ("mailbox\\.org", "Mailbox.org"),
            ("posteo", "Posteo"), ("yandex", "Yandex Mail"),
            ("qq|exmail", "Tencent QQ Mail"), ("laposte", "La Poste"),
            ("web\\.de|gmx", "United Internet (web.de / GMX)"),
            ("mail\\.ru", "Mail.ru"), ("arcor", "Vodafone / 1&1"),
            ("sendinblue|mailgun|sendgrid|postmark", "Versand-Dienst (ESP)"),
            ("security|messagelabs|proofpoint|mimecast", "Security-Gateway"),
        ]
        provider = "-"
        for pat, name in rules:
            if re.search(pat, blob):
                provider = name
                break
        out.append(("Mail-Hosting", provider))
        try:
            host = mx_hosts[0]
            ip = socket.gethostbyname(host)
            geo = dict(core.lookup_ip(ip))
            out.append(("MX-Server-IP", f"{host} -> {ip}"))
            out.append(("MX-Standort",
                        f"{geo.get('Land')} | {geo.get('Stadt')} | "
                        f"{geo.get('ISP / Anbieter')}"))
        except Exception:
            out.append(("MX-Standort", "nicht ermittelbar"))
    # Sender-IP/Land nur aus dem Header ableitbar
    out.append(("Sender-IP & Land", "nur aus dem echten Header: Option 15 "
                "(Quelltext der Mail kopieren - Outlook: Rechtsklick > "
                "Nachricht anzeigen, Gmail: Mehr > Original)"))
    out.append(("Verbundene Geraete", "NICHT ermittelbar - nur der Mail-Anbieter "
                "sieht Login/Geraete nach Authentifizierung (Google: myaccount.google.com)"))
    out.append(("Datenleck-Pruefung", "manuell: haveibeenpwned.com (kostenlos, "
                "Bestaetigungsmail noetig)"))
    return out


def lookup_username_full(username):
    username = username.strip().lstrip("@")
    if not re.match(r"^[A-Za-z0-9_.\-]{1,32}$", username):
        raise ValueError("Ungueltiger Name (a-z 0-9 _ . -)")
    out = []
    n = len(core.USERNAME_SITES)
    for i, (name, tmpl) in enumerate(core.USERNAME_SITES, 1):
        progress(f"Pruefe {name}", i, n)
        code = core.http_status(tmpl.format(u=username))
        if code == 200:
            status = c("[gefunden]", GREEN)
        elif code in (404, 410):
            status = c("[nicht gefunden]", GRAY)
        elif code in (401, 403, 429):
            status = c("[blockiert]", YELLOW)
        elif code is None:
            status = c("[Timeout]", RED)
        else:
            status = c(f"[HTTP {code}]", YELLOW)
        out.append((name, status))
    progress_done()
    return out


SEC_HEADERS = [
    ("Strict-Transport-Security", "HSTS"),
    ("Content-Security-Policy", "CSP"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "Frame-Schutz"),
    ("Referrer-Policy", "Referrer-Policy"),
    ("Permissions-Policy", "Permissions-Policy"),
]


def lookup_website_security(query):
    url = query.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    t0 = time.time()
    req = urllib.request.Request(url, headers=core.UA)
    with urllib.request.urlopen(req, timeout=core.TIMEOUT) as r:
        ms = (time.time() - t0) * 1000
        status = r.status
        final = r.geturl()
        hdrs = {k.lower(): v for k, v in r.headers.items()}
        body = r.read(150_000).decode("utf-8", "replace")
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    title = re.sub(r"\s+", " ", m.group(1)).strip()[:50] if m else "-"
    https = url.lower().startswith("https://")
    out = [
        ("URL", url),
        ("Status", f"{status}"),
        ("End-URL", final if final == url else final + "  (Redirect)"),
        ("Seitentitel", title),
        ("Antwortzeit", f"{ms:.0f} ms"),
        ("Server", hdrs.get("server", "-")),
        ("HTTPS", c("Ja", GREEN) if https else c("NEIN - unverschluesselt", RED)),
    ]
    # Sicherheits-Header + Score
    score, maxscore = 0, len(SEC_HEADERS) + 2
    missing = []
    for key, label in SEC_HEADERS:
        if key in hdrs:
            score += 1
            out.append((label, c("gesetzt", GREEN) + (f" ({hdrs[key][:40]})" if key == 'content-security-policy' else "")))
        else:
            missing.append(label)
            out.append((label, c("fehlt", RED)))
    if https:
        score += 1
    if "server" not in hdrs or not re.search(r"\d+\.\d+", hdrs.get("server", "")):
        score += 1  # keine Versions-Number im Server-Header
        out.append(("Server-Version", c("nicht verraten", GREEN)))
    else:
        out.append(("Server-Version", c("verraet Version: " + hdrs["server"], YELLOW)))
    pct = int(100 * score / maxscore)
    col = GREEN if pct >= 75 else (YELLOW if pct >= 50 else RED)
    out.append(("Sicherheits-Score", c(f"{pct} %  ({score}/{maxscore})", col)))
    if missing:
        out.append(("Fehlend", ", ".join(missing)))
    return out


def lookup_ssl(query):
    host = query.strip()
    host = re.sub(r"^https?://", "", host).split("/")[0]
    if not host:
        raise ValueError("Host noetig")
    ctx = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as s:
            cert = s.getpeercert()
            cipher = s.cipher()
            ver = s.version()
    def subs(tree, key):
        # subject/issuer = Tupel von Tupeln: ((('CN','x'),), ...)
        for entry in tree or ():
            for pair in entry:
                if pair[0] == key:
                    return pair[1]
        return None
    subject_cn = subs(cert.get("subject"), "commonName")
    issuer_org = subs(subs(cert.get("issuer"), "organizationName"), "commonName") \
        or subs(cert.get("issuer"), "commonName")
    def pd(s_):
        try:
            return datetime.strptime(s_, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        except Exception:
            return None
    nb, na = pd(cert.get("notBefore", "")), pd(cert.get("notAfter", ""))
    days = "-"
    exp_col = ""
    if na:
        days_int = (na - datetime.now(timezone.utc)).days
        days = f"{days_int} Tage"
        exp_col = c(days, GREEN if days_int > 30 else (YELLOW if days_int > 7 else RED))
    san = [v for t, v in cert.get("subjectAltName", ()) if t == "DNS"]
    out = [
        ("Host", host),
        ("CN (Zertifikat fuer)", subject_cn),
        ("Aussteller", issuer_org),
        ("Gueltig ab", nb.strftime("%d.%m.%Y") if nb else "-"),
        ("Gueltig bis", na.strftime("%d.%m.%Y") if na else "-"),
        ("Restlaufzeit", exp_col or days),
        ("TLS-Version", ver),
        ("Cipher", (cipher[0] if cipher else "-")),
        ("SANs (Alias-Namen)", ", ".join(san[:6]) + (f" (+{len(san)-6})" if len(san) > 6 else "")),
        ("Let's Encrypt/PKI", "Ja" if "letsencrypt" in (issuer_org or "").lower()
         or "R3" == subject_cn else "kommerziell/sonstiges"),
    ]
    return out


PORTS = [
    (21, "FTP"), (22, "SSH"), (23, "Telnet"), (25, "SMTP"), (53, "DNS"),
    (80, "HTTP"), (110, "POP3"), (143, "IMAP"), (443, "HTTPS"), (445, "SMB"),
    (993, "IMAPS"), (995, "POP3S"), (1433, "MSSQL"), (3306, "MySQL"),
    (3389, "RDP"), (5432, "PostgreSQL"), (5900, "VNC"), (6379, "Redis"),
    (8080, "HTTP-Alt"), (27017, "MongoDB"),
]


def lookup_ports(query):
    host = query.strip()
    if not host:
        raise ValueError("Host/IP noetig")
    try:
        ip = socket.gethostbyname(host)
    except Exception:
        raise ValueError(f"Host '{host}' nicht aufloesbar")
    # rDNS + Ping
    try:
        rdns = socket.gethostbyaddr(ip)[0]
    except Exception:
        rdns = "-"
    ping_ms = "-"
    try:
        p = subprocess_ping(ip)
        ping_ms = p
    except Exception:
        pass
    results = []
    lock = threading.Lock()
    done = [0]

    def check(port, name):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            open_ = s.connect_ex((ip, port)) == 0
        except Exception:
            open_ = False
        finally:
            s.close()
        with lock:
            done[0] += 1
            progress("Scanne Ports", done[0], len(PORTS))
            if open_:
                results.append((str(port), c(f"OFFEN  ({name})", GREEN)))

    threads = []
    for port, name in PORTS:
        t = threading.Thread(target=check, args=(port, name))
        t.start()
        threads.append(t)
        if len(threads) >= 20:
            [x.join() for x in threads]
            threads = []
    [x.join() for x in threads]
    progress_done()
    out = [("Host", host), ("IP", ip), ("rDNS", rdns), ("Ping", ping_ms)]
    out.extend(results if results else [])
    out.append(("Offene Ports", f"{len(results)} von {len(PORTS)} gescannt"))
    if not results:
        out.append(("Hinweis", "keine offenen Ports gefunden (Firewall moeglich)"))
    return out


def subprocess_ping(ip):
    import subprocess
    try:
        r = subprocess.run(["ping", "-n", "1", "-w", "1000", ip],
                           capture_output=True, timeout=6,
                           encoding="latin-1", errors="replace")
        m = re.search(r"(\d+)\s*ms", r.stdout)
        return f"{m.group(1)} ms" if m else "keine Antwort/geblockt"
    except Exception:
        return "-"


IBAN_LEN = {
    "AT": 20, "BE": 16, "CH": 21, "CZ": 24, "DE": 22, "DK": 18,
    "ES": 24, "FI": 18, "FR": 27, "GB": 22, "GR": 27, "HU": 28,
    "IE": 22, "IT": 27, "LU": 20, "NL": 18, "NO": 15, "PL": 28,
    "PT": 25, "RO": 24, "SE": 24, "SK": 24, "SI": 19, "BG": 22,
    "EE": 20, "HR": 21, "LT": 20, "LV": 21, "MT": 31, "CY": 28,
    "TR": 26, "AE": 23, "BR": 29, "SA": 24, "SM": 27, "MC": 27,
    "AD": 24, "AZ": 28, "BH": 22, "IS": 26, "KZ": 20, "LI": 21,
}


def lookup_iban(query):
    iban = re.sub(r"[\s\-]", "", query.strip()).upper()
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", iban):
        return [("Format", "FEHLER - z.B. DE89 3704 0044 0532 0130 00")], None
    country, length = iban[:2], IBAN_LEN.get(iban[:2])
    out = [("IBAN", iban),
           ("Laender-Codes", country)]
    if length is None:
        out.append(("Laender-Check", "Laendercode nicht in Tabelle (44 Laender hinterlegt)"))
    else:
        out.append(("Laender", country))
        out.append(("Laenge", f"{len(iban)} (erwartet {length}) "
                    + (c("OK", GREEN) if len(iban) == length else c("FEHLER", RED))))
    # MOD-97
    rearr = iban[4:] + iban[:4]
    num = "".join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearr)
    remainder = 0
    for ch in num:
        remainder = (remainder * 10 + int(ch)) % 97
    valid = remainder == 1
    out.append(("Pruefziffer MOD-97", c("gultig ✔", GREEN) if valid
                else c("UNgueltig ✘", RED)))
    bban = iban[4:]
    out.append(("Bankleitzahl (BBAN)", bban[:8]))
    out.append(("Formattiert", " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))))
    out.append(("Hinweis", "Gültigkeit = Format/Pruefziffer, nicht Kontobestand"))
    return out, None


COINS = ["bitcoin", "ethereum", "solana", "cardano", "ripple", "dogecoin",
         "polkadot", "chainlink", "litecoin", "tron"]


def lookup_crypto():
    ids = ",".join(COINS)
    url = (f"https://api.coingecko.com/api/v3/simple/price?ids={ids}"
           "&vs_currencies=usd,eur&include_24hr_change=true")
    d = core.http_json(url)
    names = {"bitcoin": "Bitcoin (BTC)", "ethereum": "Ethereum (ETH)",
             "solana": "Solana (SOL)", "cardano": "Cardano (ADA)",
             "ripple": "XRP", "dogecoin": "Dogecoin (DOGE)",
             "polkadot": "Polkadot (DOT)", "chainlink": "Chainlink (LINK)",
             "litecoin": "Litecoin (LTC)", "tron": "TRON (TRX)"}
    out = []
    for cid in COINS:
        v = d.get(cid, {})
        usd = v.get("usd")
        if usd is None:
            continue
        ch = v.get("usd_24h_change")
        ch_s = "-"
        if ch is not None:
            col = GREEN if ch >= 0 else RED
            ch_s = c(f"{ch:+.2f} %", col)
        price = f"{usd:,.2f} USD / {v.get('eur', 0):,.2f} EUR"
        out.append((names[cid], f"{price}   24h: {ch_s}"))
    out.append(("Quelle", "CoinGecko (kostenlos, ca. 1 Min Verzoegerung)"))
    return out


UA_PATTERNS = [
    ("Browser", [
        (r"Edg[\/]([\d.]+)", "Edge {}"),
        (r"OPR\/([\d.]+)", "Opera {}"),
        (r"Firefox\/([\d.]+)", "Firefox {}"),
        (r"Chrome\/([\d.]+)", "Chrome {}"),
        (r"Version\/([\d.]+).*Safari", "Safari {}"),
        (r"MSIE ([\d.]+)", "IE {}"),
        (r"Trident/.*rv:([\d.]+)", "IE {}"),
    ]),
    ("Betriebssystem", [
        (r"Windows NT 10\.0.*Win64", "Windows 10/11 (64-bit)"),
        (r"Windows NT 10\.0", "Windows 10/11"),
        (r"Windows NT 6\.3", "Windows 8.1"),
        (r"Windows NT 6\.1", "Windows 7"),
        (r"Mac OS X ([\d_]+)", "macOS {}"),
        (r"Android ([\d.]+)", "Android {}"),
        (r"iPhone OS ([\d_]+)", "iOS {}"),
        (r"iPad.*OS ([\d_]+)", "iPadOS {}"),
        (r"CrOS", "ChromeOS"),
        (r"Linux", "Linux"),
    ]),
    ("Geraet", [
        (r"iPhone", "iPhone"),
        (r"iPad", "iPad"),
        (r"Android.*Mobile", "Android-Handy"),
        (r"Android", "Android-Tablet"),
        (r"Windows", "PC/Windows"),
        (r"Macintosh|Mac OS", "Mac"),
        (r"bot|crawler|spider|curl|python-requests|wget", "Bot/Script"),
    ]),
]


def lookup_useragent(query):
    ua = query.strip()
    if not ua:
        return None, "UA-String noetig"
    out = [("User-Agent", ua[:120])]
    if len(ua) > 120:
        out.append(("", "..."))
    for section, pats in UA_PATTERNS:
        found = "-"
        for pat, repl in pats:
            m = re.search(pat, ua, re.I)
            if m:
                found = repl.format(*(m.groups() or ())) if "{}" in repl else repl
                break
        out.append((section, found))
    bots = bool(re.search(r"bot|crawler|spider|curl|python|wget|scanner", ua, re.I))
    out.append(("Automatisiert", c("JA - Bot/Script erkannt", YELLOW) if bots
                else c("Nein - sieht nach normalem Browser aus", GREEN)))
    return out, None


def lookup_github(query):
    name = query.strip().lstrip("@")
    if not re.match(r"^[A-Za-z0-9\-]{1,39}$", name):
        return None, "Ungueltiger GitHub-Name (a-z, 0-9, -)"
    try:
        d = core.http_json(f"https://api.github.com/users/{name}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, f"Benutzer '{name}' nicht gefunden"
        if e.code == 403:
            return None, "GitHub-Rate-Limit erreicht (60 Abfragen/Std ohne Login)"
        return None, f"GitHub API: HTTP {e.code}"
    last_repo = "-"
    try:
        repos = core.http_json(
            f"https://api.github.com/users/{name}/repos?sort=pushed&per_page=1")
        if repos:
            last_repo = f"{repos[0]['name']} (push: {repos[0]['pushed_at'][:10]})"
    except Exception:
        pass
    out = [
        ("Login", d.get("login")),
        ("Name", d.get("name") or "-"),
        ("Typ", d.get("type")),
        ("Bio", (d.get("bio") or "-")[:70]),
        ("Ort", d.get("location") or "-"),
        ("Repos", d.get("public_repos")),
        ("Follower", d.get("followers")),
        ("Folgt", d.get("following")),
        ("Gegründet", (d.get("created_at") or "")[:10]),
        ("Profil", d.get("html_url")),
        ("Letztes Repo", last_repo),
    ]
    if d.get("hireable"):
        out.append(("Verfuegbar", "ja (hireable)"))
    return out, None


def read_multiline():
    print(f"\n   {CYAN}E-Mail-Header einfuegen:{R} {GRAY}Quelltext der Nachricht")
    print(f"   mehrzeilig kopieren/einfuegen, dann leere Zeile = auswerten{R}")
    print(f"   {GRAY}   Outlook: Rechtsklick auf Mail > 'Nachricht anzeigen'")
    print(f"   Gmail:   ... > 'Original anzeigen'  |  Thunderbird: 'Quelltext' ansehen{R}")
    print(f"   {GRAY}   (bzw. 'View source', 'Show headers'{R}")
    print(f"\n   {YELLOW}Zum Beenden und Auswerten: leere Zeile druecken{R}")
    lines = []
    while True:
        try:
            l = input(f"   {YELLOW}|{R} ")
        except (EOFError, KeyboardInterrupt):
            break
        if l.strip() == "":
            if lines:
                break
            continue
        lines.append(l)
    return "\n".join(lines)


def analyze_email_header(text):
    """Extrahiert aus einem vollen Mail-Header: Ursprung-IP, Geo, Hops, Auth, Client."""
    if not text.strip():
        return None, "kein Header eingefuegt"
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    unf = []
    for l in lines:  # Fortsetzungszeilen anfuegen (RFC 5322 unfolding)
        if l[:1] in (" ", "\t") and unf:
            unf[-1] += " " + l.strip()
        else:
            unf.append(l)

    def find_val(prefix):
        for l in unf:
            if l.lower().startswith(prefix):
                return l.split(":", 1)[1].strip() or "-"
        return "-"

    out = []
    out.append(("Betreff", find_val("subject")[:60]))
    out.append(("Von", find_val("from")[:60]))
    out.append(("An", find_val("to")[:60]))
    out.append(("Return-Path", find_val("return-path")[:60]))
    out.append(("Datum", find_val("date")[:45]))
    mid = find_val("message-id")
    mm = re.search(r"@([A-Za-z0-9.\-]+)", mid)
    out.append(("Message-ID-Domane", mm.group(1) if mm else "-"))
    # Authentifizierungsbefunde
    auth_blob = " ".join(l for l in unf
                         if "authentication-results" in l.lower()
                         or l.lower().startswith("received-spf"))
    for key in ("spf", "dkim", "dmarc"):
        m = re.search(rf"\b{key}=([a-z0-9\-]+)", auth_blob, re.I)
        v = m.group(1).lower() if m else "kein Ergebnis"
        col = GREEN if v in ("pass", "best") else (
            RED if v in ("fail", "softfail", "permerror") else YELLOW)
        out.append((f"Auth {key.upper()}", c(v, col)))
    # Empfangskette: Header-Liste ist top=letzter Hop, unten=erster Hop
    rec = [l for l in unf if l.lower().startswith("received")]
    out.append(("Empfangs-Hops", len(rec)))
    chrono = list(reversed(rec))  # chronologisch: Sender -> Empfaenger
    origin = None
    for i, l in enumerate(chrono, 1):
        ips = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}", l)
        if origin is None and ips:
            origin = ips[0]
        if i <= 6:
            m = re.search(r"from\s+(\S+?)[\s(].*?by\s+(\S+?)[\s(]", l)
            if m:
                out.append((f"Hop {i}", f"{m.group(1)[:30]} -> {m.group(2)[:30]}"))
            else:
                out.append((f"Hop {i}", re.sub(r"\s+", " ", l)[:66]))
    if len(chrono) > 6:
        out.append(("+ mehr", f"{len(chrono) - 6} weitere Hops"))
    # Ursprungs-IP + Geo
    if origin:
        out.append(("Ursprungs-IP (Sender)", origin))
        try:
            out.append(("rDNS", socket.gethostbyaddr(origin)[0]))
        except Exception:
            out.append(("rDNS", "-"))
        import ipaddress
        try:
            is_private = ipaddress.ip_address(origin).is_private
        except ValueError:
            is_private = False
        if is_private:
            out.append(("Standort", "PRIVATE IP (LAN/Heimnetz) - kein "
                        "oeffentlicher Standort da"))
            out.append(("Bedeutung", "Sender war im lokalen Netz oder es ist "
                        "ein interner Webmail-Hop - die oeffentliche IP steht "
                        "in einem aesseren Hop"))
        else:
            try:
                geo = dict(core.lookup_ip(origin))
                out.append(("Land", geo.get("Land")))
                out.append(("Stadt", geo.get("Stadt")))
                out.append(("ISP / Anbieter", geo.get("ISP / Anbieter")))
                out.append(("ASN", geo.get("ASN")))
                out.append(("Koordinaten", geo.get("Koordinaten")))
            except Exception as e:
                out.append(("Geo-Abfrage", f"Fehler ({type(e).__name__})"))
    else:
        out.append(("Ursprungs-IP", "keine IPv4 im Header gefunden"))
    # Client-Schätzung: explizite Client-Header zuerst, Infrastruktur zuletzt
    low = "\n".join(unf).lower()
    xm = find_val("x-mailer").lower()
    if "outlook" in xm or "x-microsoft" in low or "microsoft outlook" in low:
        client = "Outlook / Microsoft 365"
    elif "phpmailer" in low:
        client = "PHPMailer (Server/Massen-Mail)"
    elif "apple mail" in xm or "x-mail-client" in low or "iphone" in low:
        client = "Apple Mail (iOS/macOS)"
    elif "thunderbird" in low or "thunderbird" in xm:
        client = "Mozilla Thunderbird"
    elif "postfix" in low or "exim" in low:
        client = "Mailserver-Software (Postfix/Exim)"
    elif "gmail" in low or "mx.google.com" in low:
        client = "Gmail-Infrastruktur (Web/App)"
    elif "yahoo" in low:
        client = "Yahoo Mail"
    else:
        client = "-"
    out.append(("Client (geschätzt)", client))
    xmailer = find_val("x-mailer")
    if xmailer != "-":
        out.append(("X-Mailer", xmailer[:50]))
    out.append(("Hinweis", "IP/Land = Mail-Server des Senders, NICHT der Person"))
    return out, None


def snowflake_time(sid):
    """Discord-Snowflake-ID -> Erstellungsdatum."""
    try:
        ms = (int(sid) >> 22) + 1420070400000
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
            "%d.%m.%Y %H:%M UTC")
    except Exception:
        return "-"


def lookup_discord_webhook(query):
    url = query.strip()
    m = re.search(r"discord(?:app)?\.com/api(?:/v\d+)?/webhooks/(\d+)/([\w-]+)",
                  url)
    if not m:
        return None, ("volle Webhook-URL noetig: "
                      "discord.com/api/webhooks/ID/TOKEN - nur EIGENE URLs "
                      "pruefen (URL wie Passwort behandeln!)")
    wid, token = m.groups()
    try:
        d = core.http_json(f"https://discord.com/api/v10/webhooks/{wid}/{token}")
    except urllib.error.HTTPError as e:
        if e.code in (401, 404):
            return None, "Webhook nicht gefunden / Token ungueltig / abgelaufen"
        if e.code == 429:
            return None, "Discord-Rate-Limit - kurz warten"
        return None, f"Discord API: HTTP {e.code}"
    return [
        ("Status", "gueltig und erreichbar"),
        ("Name", d.get("name") or "-"),
        ("Server-ID", d.get("guild_id") or "-"),
        ("Kanal-ID", d.get("channel_id") or "-"),
        ("Avatar-Hash", d.get("avatar") or "-"),
        ("Webhook-ID", d.get("id")),
        ("Typ", "Standard (mit Bearbeiten)"),
        ("Hinweis", "Nur gelesen - nichts gesendet. URL = Passwort, "
                    "nicht weitergeben!"),
    ], None


def lookup_discord_status():
    st = core.http_json("https://discordstatus.com/api/v2/status.json")
    indicator = st.get("status", {}).get("indicator", "?")
    desc = st.get("status", {}).get("description", "-")
    col = GREEN if indicator == "none" else (YELLOW if indicator == "minor"
                                             else RED)
    out = [("Gesamtstatus", c(desc, col)),
           ("Betroffene Bereiche", str(st.get("status", {}).get("code", "-")))]
    comps = st.get("components", [])
    oper = [x for x in comps if x.get("status") == "operational"]
    bad = [x for x in comps if x.get("status") != "operational"]
    if comps:
        out.append(("Komponenten", f"{len(oper)}/{len(comps)} betriebsbereit"))
    for x in bad[:6]:
        out.append((x.get("name", "?")[:26],
                    c(x.get("status", "?"), RED)))
    if not comps:
        out.append(("Komponenten", "Statuspage liefert keine Detail-Liste "
                    "(nur Gesamtstatus)"))
    try:
        inc = core.http_json(
            "https://discordstatus.com/api/v2/incidents/unresolved.json")
        for i in inc.get("incidents", [])[:2]:
            out.append(("Offener Vorfall", f'{i.get("name")} - {i.get("status")}'))
        if not inc.get("incidents"):
            out.append(("Offene Vorgaenge", "keine"))
    except Exception:
        pass
    out.append(("Quelle", "discordstatus.com (offiziell)"))
    return out


WMO = {
    0: "Klar", 1: "Ueberwiegend klar", 2: "Teilweise bewoelkt", 3: "Bedeckt",
    45: "Nebel", 46: "Gefrierender Nebel", 48: "Reifnebel",
    51: "Leichter Niesel", 53: "Niesel", 55: "Starker Niesel",
    56: "Gefrierender Niesel", 57: "Gefrierender Niesel",
    61: "Leichter Regen", 63: "Regen", 65: "Starker Regen",
    66: "Gefrierender Regen", 67: "Gefrierender Regen",
    71: "Leichter Schnee", 73: "Schnee", 75: "Starker Schnee",
    77: "Schneegriesel", 80: "Regenschauer", 81: "Kraeftige Schauer",
    82: "Heftige Schauer", 85: "Schneeschauer", 86: "Kraeftige Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "Schweres Gewitter",
}


def lookup_weather(query):
    city = query.strip()
    if not city:
        return None, "Stadt noetig"
    geo = core.http_json(
        "https://geocoding-api.open-meteo.com/v1/search?name="
        + _up.quote(city) + "&count=1&language=de&format=json")
    res = geo.get("results")
    if not res:
        return None, f"Ort '{city}' nicht gefunden"
    g = res[0]
    lat, lon = g["latitude"], g["longitude"]
    w = core.http_json(
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        "precipitation,weather_code,wind_speed_10m,is_day&timezone=auto")
    cur = w.get("current", {})
    code = cur.get("weather_code", -1)
    temp = cur.get("temperature_2m")
    return [
        ("Ort", f'{g.get("name")}, {g.get("country")} '
                f'({g.get("admin1") or ""})'),
        ("Zustand", WMO.get(code, f"WMO-Code {code}")
         + ("  (Tag)" if cur.get("is_day") else "  (Nacht)")),
        ("Temperatur", f"{temp} °C"),
        ("Gefuehlt", f'{cur.get("apparent_temperature")} °C'),
        ("Luftfeuchte", f'{cur.get("relative_humidity_2m")} %'),
        ("Wind", f'{cur.get("wind_speed_10m")} km/h'),
        ("Niederschlag", f'{cur.get("precipitation")} mm'),
        ("Ortszeit", w.get("current", {}).get("time", "-")),
        ("Quelle", "open-meteo.com (kostenlos, kein Key)"),
    ], None


def lookup_rates(query):
    q = query.strip().upper()
    nums = re.findall(r"\d+(?:[.,]\d+)?", q)
    codes = re.findall(r"[A-Z]{3}", q)
    amount = float(nums[0].replace(",", ".")) if nums else 1.0
    if not codes:
        return None, "z.B. '100 USD EUR' eingeben"
    base = codes[0]
    quote = codes[1] if len(codes) > 1 else ("EUR" if base != "EUR" else "USD")
    d = core.http_json(f"https://open.er-api.com/v6/latest/{base}")
    if d.get("result") != "success":
        return None, f"Unbekannte Waehrung: {base}"
    rates = d.get("rates", {})
    if quote not in rates:
        return None, f"Unbekannte Zielwaehrung: {quote}"
    rate = rates[quote]
    conv = amount * rate
    return [
        ("Rechnung", f"{amount:g} {base} -> {conv:,.2f} {quote}"),
        ("Kurs", f"1 {base} = {rate:,.4f} {quote}"),
        ("Rueckwaerts", f"1 {quote} = {1 / rate:,.4f} {base}"),
        ("Basis", base),
        ("Stand", d.get("time_last_update_utc", "-")),
        ("Quelle", "open.er-api.com (ECB-Daten, kostenlos)"),
    ], None


def lookup_wikipedia(query):
    term = query.strip()
    if not term:
        return None, "Suchbegriff noetig"
    try:
        d = core.http_json(
            "https://de.wikipedia.org/api/rest_v1/page/summary/"
            + _up.quote(term.replace(" ", "_")))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, f"Kein Artikel '{term}' gefunden"
        return None, f"Wikipedia API: HTTP {e.code}"
    if d.get("type") == "disambiguation":
        return [("Hinweis", "Begriffsklaerungsseite - genauer suchen"),
                ("Titel", d.get("title")),
                ("Link", d.get("content_urls", {}).get("desktop", {}).get("page"))], None
    thumb = (d.get("thumbnail") or {}).get("source", "-")
    return [
        ("Titel", d.get("title")),
        ("Untertitel", d.get("description") or "-"),
        ("Zusammenfassung", (d.get("extract") or "-")[:400]),
        ("Artikel-Link", d.get("content_urls", {}).get("desktop", {}).get("page")),
        ("Vorschaubild", thumb if len(str(thumb)) < 90 else str(thumb)[:87] + "..."),
    ], None


def lookup_youtube(query):
    q = query.strip()
    vid = None
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})", q)
    if m:
        vid = m.group(1)
    elif re.fullmatch(r"[\w-]{11}", q):
        vid = q
    if not vid:
        return None, "YouTube-Link oder 11-stellige Video-ID noetig"
    try:
        d = core.http_json(
            "https://www.youtube.com/oembed?format=json&url="
            + _up.quote(f"https://www.youtube.com/watch?v={vid}", safe=""))
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            return None, "Video nicht gefunden / privat / gesperrt"
        return None, f"YouTube API: HTTP {e.code}"
    return [
        ("Titel", d.get("title")),
        ("Kanal", d.get("author_name")),
        ("Anbieter", d.get("provider_name")),
        ("Video-ID", vid),
        ("Link", f"https://www.youtube.com/watch?v={vid}"),
        ("Vorschaubild", str(d.get("thumbnail_url", "-"))[:80]),
    ], None


def _vcard_fn(entities):
    for ent in entities or []:
        vc = ent.get("vcardArray")
        if vc and len(vc) > 1:
            for item in vc[1]:
                if item and item[0] == "fn":
                    return item[3]
    return None


def lookup_ip_network(query):
    ip = query.strip()
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
        return None, "IPv4-Adresse noetig (z.B. 8.8.8.8)"
    try:
        d = core.http_json("https://rdap.org/ip/" + ip)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, "Kein RDAP-Eintrag fuer diese IP"
        return None, f"RDAP: HTTP {e.code}"
    except Exception as e:
        return None, f"RDAP-Fehler ({type(e).__name__})"
    org = None
    for ent in d.get("entities", []):
        roles = ent.get("roles", [])
        if any(r in roles for r in ("registrant", "holder", "operator")):
            org = _vcard_fn([ent]) or ent.get("handle")
            if org:
                break
    if not org:
        for ent in d.get("entities", []):
            org = _vcard_fn([ent])
            if org:
                break
    events = {e.get("eventAction"): e.get("eventDate")
              for e in d.get("events", [])}
    cidrs = ", ".join(c.get("v4prefix", "") + "/" + str(c.get("length", ""))
                      for c in d.get("cidr0_cidrs", []))
    return [
        ("IP", ip),
        ("Netzname", d.get("name") or "-"),
        ("Handle", d.get("handle") or "-"),
        ("Land", d.get("country") or "-"),
        ("Bereich", cidrs or f'{d.get("startAddress")} - {d.get("endAddress")}'),
        ("Organisation", org or "-"),
        ("Status", ", ".join(d.get("status", [])) or "-"),
        ("Registriert", events.get("registration", "-")),
        ("Ende der Ressource", events.get("expiration", "-")),
        ("Registry", "RIPE/ARIN/APNIC/LACNIC via rdap.org"),
    ], None


def lookup_traceroute(query):
    host = query.strip()
    if not host:
        return None, "Host/IP noetig"
    import subprocess
    try:
        r = subprocess.run(
            ["tracert", "-d", "-h", "12", "-w", "700", host],
            capture_output=True, timeout=90,
            encoding="latin-1", errors="replace")
    except subprocess.TimeoutExpired:
        return None, "Traceroute-Timeout (>90s)"
    except FileNotFoundError:
        return None, "tracert nicht gefunden (nur Windows)"
    out = [("Ziel", host)]
    hop = 0
    for line in r.stdout.splitlines():
        m = re.match(r"^\s*(\d+)\s+(.*)$", line)
        if not m:
            continue
        hop = int(m.group(1))
        rest = m.group(2)
        times = re.findall(r"(<?\s*\d+)\s*ms", rest)
        target_m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})\s*$", rest)
        target = target_m.group(1) if target_m else ""
        if times:
            clean = [t.replace(" ", "") + " ms" for t in times[:3]]
            out.append((f"Hop {hop}",
                        f'{", ".join(clean)}  {target}'))
        else:
            out.append((f"Hop {hop}", "Zeitueberschreitung (*)"))
    if hop == 0:
        out.append(("Hinweis", "keine Hops auswertbar"))
    out.append(("Hops gesamt", hop))
    out.append(("Hinweis", "Privates Netz (192.168.x) = eigener Router"))
    return out, None


def lookup_network_local():
    import subprocess
    try:
        r = subprocess.run(["ipconfig"], capture_output=True, timeout=15,
                           encoding="latin-1", errors="replace")
        text = r.stdout
    except Exception as e:
        return None, f"ipconfig fehlgeschlagen ({type(e).__name__})"
    ipv4 = re.findall(r"IPv4[^:]*:\s*([\d.]+)", text, re.I)
    gw = re.findall(r"(?:Standardgateway|Default Gateway)[^:]*:\s*([\d.]+)",
                    text, re.I)
    dns = re.findall(r"(?:DNS[- ]Server|Preferred DNS|Bevorzugter DNS|"
                     r"Alternativer DNS|Secondary DNS)[^:]*:\s*([\d.]+)",
                     text, re.I)
    try:
        suffix = os.environ.get("USERDNSDOMAIN", "-")
    except Exception:
        suffix = "-"
    return [
        ("Hostname", socket.gethostname()),
        ("Benutzer", os.environ.get("USERNAME", "-")),
        ("IPv4 (alle Adapter)", ", ".join(ipv4) or "-"),
        ("Gateway", ", ".join(x for x in gw if x != "0.0.0.0") or "-"),
        ("DNS-Server", ", ".join(dns) or "-"),
        ("DNS-Domane", suffix),
        ("Hinweis", "192.168.x/10.x/172.16-31.x = private LAN-Adresse"),
        ("Oeffentliche IP", "Option 1 oder 16 nutzen"),
    ], None


# ================================================================ RUNNER
def lookup_my_ip_links():
    """Eigene oeffentliche IP + Klick-Links, die beim Oeffnen die IP zeigen."""
    lines = core.lookup_ip("")  # leere Abfrage = eigene IP via ipwho.is
    ip = dict(lines).get("IP-Adresse")
    lines.append(("Direkt-Link (nur IP)", "https://api.ipify.org"))
    lines.append(("Link mit Ort/ISP", "https://ipinfo.io/" + (ip or "")))
    lines.append(("Alternativ", "https://whatismyipaddress.com"))
    lines.append(("Hinweis", "Diese Links zeigen IMMER die eigene IP des "
                 "Besuchers - da wird nichts fremdes mitgeschrieben"))
    return lines

def run_lookup(label, fn, *args, raw=False):
    header(label)
    try:
        with Spinner(label):
            result = fn(*args)
    except Exception as ex:
        err(str(ex))
        return
    if raw:
        show_results(result)
    elif isinstance(result, tuple):
        lines, fehler = result
        if fehler:
            err(fehler)
            return
        show_results(lines)
    else:
        show_results(result)
    print()


def prompt(text):
    try:
        return input(f"\n   {YELLOW}▸ {BOLD}{text}{R}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def matrix_rain(duration=1.2):
    """Live-Matrix-Regen: eis-cyan Koepfe, silberne Spuren, Glyphen-Flicker."""
    import shutil
    sz = shutil.get_terminal_size((100, 32))
    cols_n = max(30, min(sz.columns - 1, 140))
    rows_n = max(12, min(sz.lines - 2, 34))
    glyphs = "0123456789:·.=*+-<>|#/\\%@$XURK"
    heads = [[random.randint(-rows_n, rows_n), random.uniform(0.7, 1.7)]
             for _ in range(cols_n)]
    colchars = [[random.choice(glyphs) for _ in range(rows_n)]
                for _ in range(cols_n)]
    end = time.time() + duration
    colors_map = {4: "\x1b[1;96m", 3: "\x1b[1;97m", 2: "\x1b[37m",
                  1: "\x1b[2;37m", 0: "\x1b[0m"}
    sys.stdout.write("\x1b[?25l\x1b[2J\x1b[H")
    sys.stdout.flush()
    while time.time() < end:
        intens = [[0] * rows_n for _ in range(cols_n)]
        for x in range(cols_n):
            y, sp = heads[x]
            y += sp
            if y - 13 > rows_n:
                y = random.randint(-rows_n, -3)
                colchars[x] = [random.choice(glyphs) for _ in range(rows_n)]
            heads[x][0] = y
            yi = int(y)
            for t in range(12):
                yy = yi - t
                if 0 <= yy < rows_n:
                    intens[x][yy] = (4 if t == 0 else
                                     3 if t < 3 else
                                     2 if t < 6 else 1)
            if 0 <= yi < rows_n and random.random() < 0.4:
                colchars[x][yi] = random.choice(glyphs)
        frame = []
        for yy in range(rows_n):
            row, cur = [], None
            for x in range(cols_n):
                it = intens[x][yy]
                if it != cur:
                    cur = it
                    row.append(colors_map[it])
                row.append(colchars[x][yy] if it else " ")
            row.append("\x1b[0m")
            frame.append("".join(row))
        sys.stdout.write("\x1b[H" + "\n".join(frame) + "\x1b[J")
        sys.stdout.flush()
        time.sleep(0.045)
    sys.stdout.write("\x1b[2J\x1b[H\x1b[?25h")
    sys.stdout.flush()


MATRIX_WM = [
    r"    ██╗      ██████╗  ██████╗ ████████╗",
    r"    ██║     ██╔═══██╗██╔═══██╗╚══██╔══╝",
    r"    ██║     ██║   ██║██║   ██║   ██║   ",
    r"    ██║     ██║   ██║██║   ██║   ██║   ",
    r"    ███████╗╚██████╔╝╚██████╔╝   ██║   ",
    r"    ╚══════╝ ╚═════╝  ╚═════╝    ╚═╝   ",
    r"     MATRIX LIVE  ☠  TASTE = ENDE",
]


def matrix_live():
    """Vollbild-Matrix (Live) - laeuft bis zur naechsten Taste.
    Ohne Konsole (Pipe/Tests): begrenzt via LOOKUP_MATRIX_SECS (Default 5s)."""
    import shutil
    sz = shutil.get_terminal_size((110, 34))
    cols_n = max(30, min(sz.columns - 1, 150))
    rows_n = max(16, min(sz.lines - 2, 42))
    glyphs = "0123456789ABCDEF#$%&*<>/\\|+=:."
    y = [random.uniform(-rows_n, rows_n) for _ in range(cols_n)]
    sp = [random.uniform(0.55, 1.7) for _ in range(cols_n)]
    trail = [random.randint(8, 16) for _ in range(cols_n)]
    is_green = [i % 6 == 3 for i in range(cols_n)]
    chars = [[random.choice(glyphs) for _ in range(rows_n)]
             for _ in range(cols_n)]
    cmap_red = {4: "\x1b[1;97m", 3: "\x1b[91m", 2: "\x1b[31m",
                1: "\x1b[2;31m", 0: "\x1b[0m"}
    cmap_green = {4: "\x1b[1;97m", 3: "\x1b[92m", 2: "\x1b[32m",
                  1: "\x1b[2;32m", 0: "\x1b[0m"}
    cmaps = [cmap_green if g else cmap_red for g in is_green]
    use_key, msvcrt = False, None
    if sys.stdin.isatty():
        try:
            import msvcrt as _mk
            msvcrt = _mk
            use_key = True
        except Exception:
            use_key = False
    deadline = None
    if not use_key:
        try:
            deadline = time.time() + float(
                os.environ.get("LOOKUP_MATRIX_SECS", "5"))
        except ValueError:
            deadline = time.time() + 5
    surges = {}
    next_surge = time.time() + 1.0
    ov_col = BOLD + WARN
    sys.stdout.write("\x1b[?25l\x1b[2J\x1b[H")
    sys.stdout.flush()
    frames, t0, fps_txt = 0, time.time(), 0
    while True:
        if use_key:
            if msvcrt.kbhit():
                msvcrt.getch()
                break
        elif deadline is not None and time.time() >= deadline:
            break
        now = time.time()
        if now >= next_surge:
            surges[random.randrange(cols_n)] = 8
            next_surge = now + random.uniform(1.4, 3.0)
        intens = [[0] * rows_n for _ in range(cols_n)]
        for x in range(cols_n):
            y[x] += sp[x]
            if y[x] - trail[x] > rows_n:
                y[x] = random.uniform(-trail[x] - 2, -1)
                chars[x] = [random.choice(glyphs) for _ in range(rows_n)]
            if x in surges:
                surges[x] -= 1
                if surges[x] <= 0:
                    del surges[x]
                for yy in range(rows_n):
                    intens[x][yy] = 3
            yi = int(y[x])
            for t in range(trail[x]):
                yy = yi - t
                if 0 <= yy < rows_n:
                    intens[x][yy] = (4 if t == 0 else
                                     3 if t < 3 else
                                     2 if t < 7 else 1)
            if random.random() < 0.3:
                chars[x][random.randrange(rows_n)] = random.choice(glyphs)
        # Wasserzeichen mittig + HUD unten
        overlay = {}
        wm_w = max(len(s) for s in MATRIX_WM)
        wm_c = max(0, (cols_n - wm_w) // 2)
        wm_r = max(0, (rows_n - len(MATRIX_WM)) // 2 - 1)
        for wi, wline in enumerate(MATRIX_WM):
            rr = wm_r + wi
            if not 0 <= rr < rows_n:
                continue
            for wc_, wch in enumerate(wline):
                cc = wm_c + wc_
                if wch != " " and 0 <= cc < cols_n:
                    overlay[(rr, cc)] = (wch, ov_col)
        lit = 0
        for x in range(cols_n):
            for yy in range(rows_n):
                if intens[x][yy]:
                    lit += 1
        frames += 1
        if frames % 15 == 0 and now > t0:
            fps_txt = int(frames / (now - t0))
        hud = (f" MATRIX LIVE ▌ FPS {fps_txt:>2} ▌ Glyphen {lit:>4} ▌ "
               + ("Taste druecken = Ende" if use_key
                  else f"Auto-Ende {int(max(0, (deadline or now) - now)) + 1}s"))
        hud = hud.ljust(cols_n)[:cols_n]
        for k, ch in enumerate(hud):
            if ch != " ":
                overlay[(rows_n - 1, k)] = (ch, FIRE)
        frame = []
        for yy in range(rows_n):
            parts, cur = [], None
            for x in range(cols_n):
                o = overlay.get((yy, x))
                if o is not None:
                    ch, colr = o
                else:
                    it = intens[x][yy]
                    ch = chars[x][yy] if it else " "
                    colr = cmaps[x][it]
                if colr != cur:
                    cur = colr
                    parts.append(colr)
                parts.append(ch)
            parts.append("\x1b[0m")
            frame.append("".join(parts))
        sys.stdout.write("\x1b[H" + "\n".join(frame) + "\x1b[J")
        sys.stdout.flush()
        time.sleep(0.045)
    sys.stdout.write("\x1b[2J\x1b[H\x1b[?25h")
    sys.stdout.flush()
    print(f"   {BLOOD}{BOLD}☠{R} {WARN}Matrix-Live beendet{R} "
          f"{DIM}- 'm' startet ihn jederzeit neu{R}")


def scramble_reveal(lines, steps=13):
    """Logo-Buchstaben materialisieren sich aus Zufallskrammel."""
    import random
    charset = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#%&*+=<>/\\|"
    sys.stdout.write("\x1b[?25l\x1b[2J\x1b[H")
    maxlen = max((len(l) for l in lines), default=70)
    for step in range(steps + 1):
        prog = (step / steps) * (maxlen + 8)
        out = []
        for li, line in enumerate(lines):
            col = GRADIENT[li % len(GRADIENT)]
            buf = []
            for i, ch in enumerate(line):
                if i < prog - 6:
                    buf.append(ch)
                elif i < prog + 4:
                    buf.append(random.choice(charset) if ch != " "
                               else random.choice("  ·."))
                elif ch == " ":
                    buf.append(" ")
                else:
                    buf.append(random.choice(" .·"))
            out.append(col + "".join(buf) + "\x1b[0m")
        sys.stdout.write("\x1b[H" + "\n".join(out) + "\x1b[J")
        sys.stdout.flush()
        time.sleep(0.05)
    sys.stdout.write("\x1b[?25h\n")
    sys.stdout.flush()


def glitch_banner(lines, frames=5):
    """Banner glitcht horizontal: Versatz + Krammel, letzter Frame sauber."""
    charset = "█▓▒░#%&*+=<>/\\|0123456789ABCDEF"
    for fr in range(frames):
        out = []
        glitch = fr < frames - 1
        for li, line in enumerate(lines):
            col = GRADIENT[li % len(GRADIENT)]
            txt = line
            if glitch and random.random() < 0.75:
                sh = random.randint(-6, 6)
                txt = txt[sh:] + txt[:sh]
                txt = "".join(
                    random.choice(charset) if ch != " " and random.random() < 0.12
                    else ch for ch in txt)
                if random.random() < 0.3:
                    col = "\x1b[7m" + col  # inverser Flash
            out.append(col + txt + R)
        sys.stdout.write("\x1b[H" + "\n".join(out) + "\x1b[J")
        sys.stdout.flush()
        time.sleep(0.055)
    clean = [GRADIENT[li % len(GRADIENT)] + ln + R
             for li, ln in enumerate(lines)]
    sys.stdout.write("\x1b[H" + "\n".join(clean) + "\x1b[J\n")
    sys.stdout.flush()


def boot_sequence():
    """Boot-Zeilen im Spectre-Look: Silber-Angus + [ ZUGRIFF OK ]."""
    import random as _r
    stages = [
        "Kernmodule / Farbprofil",
        f"Lookup-Engines    [{len(MENU_ITEMS)} Abfragen]",
        "Geo-IP + Karten-Renderer (Welt)",
        "DNS-Resolver      UDP + DoH-Fallback",
        "Discord-API       Bot + Invites + Webhooks",
        "Header-Analyzer   E-Mail-Forensik",
        "Nur-Lese-Modus    erzwungen",
        "Matrix-Renderer   live",
        "Spectre-Banner    aktiv",
    ]
    for s in stages:
        sys.stdout.write(f"   {CYAN}▲{R} {WHITE}{s:<46}{R}")
        sys.stdout.flush()
        time.sleep(0.07 + _r.random() * 0.13)
        sys.stdout.write(f"{CYAN}{BOLD}[ ZUGRIFF OK ]{R}\n")
        sys.stdout.flush()
    print(f"   {BLOOD}███{WARN}▒{FIRE}▓ {BOLD}{WARN}SYSTEM BEREIT - SPECTRE ONLINE "
          f"{FIRE}▓{WARN}▒{BLOOD}███{R}")


def show_start_banner():
    os.system("title SPECTRE // Lookup Tool v" + VER)
    try:
        matrix_rain(1.4)
        scramble_reveal(SPLASH_LINES, steps=14)
        print(f"        {FIRE}v{VER} {GRAY}·{R} {WARN}Terminal Lookup Suite{R}")
        time.sleep(0.15)
        splash_progress(2.1)
        hazard_flash()
        glitch_banner(SPLASH_LINES, frames=6)
        boot_sequence()
        user = os.environ.get("USERNAME", "User")
        host = socket.gethostname()
        slow_print(
            f"   {BLOOD}☠ {WARN}Bereit, {BOLD}{user}@{host}{R}{DIM} - "
            f"{len(MENU_ITEMS)} Abfragen, Nur-Lese-Modus{R}", 0.004)
        print()
    except KeyboardInterrupt:
        pass
    sys.stdout.write("\x1b[?25h")
    sys.stdout.flush()


# Farbige Wrappers fuer die neuen Social-Lookups (Werte bleiben oeffentlich)
def lookup_snapchat_cli(q):
    out = []
    for k, v in core.lookup_snapchat(q):
        s = str(v)
        if s.startswith("nicht gefunden"):
            s = f"{GRAY}{s}{R}"
        elif s.startswith("gesperrt"):
            s = f"{WARN}{s}{R}"
        elif s.startswith("oeffentliches"):
            s = f"{ACID}{s}{R}"
        out.append((k, s))
    return out


def lookup_account_view_cli(q):
    out = []
    for k, v in core.lookup_account_view(q):
        s = str(v)
        if s.startswith("nicht gefunden"):
            s = f"{GRAY}{s}{R}"
        elif s.startswith("gesperrt"):
            s = f"{WARN}{s}{R}"
        elif s.startswith(("kein oeffentlicher", "nur Login-Wand")):
            s = f"{DIM}{s}{R}"
        elif s.startswith(("Fehler", "HTTP", "unerwartet")):
            s = f"{RED}{s}{R}"
        elif k == "Hinweis":
            s = f"{GRAY}{s}{R}"
        out.append((k, s))
    return out


MENU_ACTIONS = {
    "1":  ("IP & Geo-Karte", lambda q: lookup_ip_full(q), True),
    "2":  ("E-Mail (erweitert)", lambda q: lookup_email_full(q), True),
    "3":  ("Benutzername", lambda q: lookup_username_full(q), True),
    "4":  ("DNS / Domain", lambda q: lookup_dns_full(q), True),
    "5":  ("Telefonnummer", lambda q: core_or_cli_phone(q), True),
    "6":  ("MAC-Adresse", lambda q: lookup_mac2(q), True),
    "7":  ("Website-Sicherheit", lambda q: lookup_website_security(q), True),
    "8":  ("SSL-Zertifikat", lambda q: lookup_ssl(q), True),
    "9":  ("Port-Check", lambda q: lookup_ports(q), True),
    "10": ("IBAN-Pruefung", lambda q: lookup_iban(q), True),
    "11": ("Krypto-Kurse", lambda q: lookup_crypto(), False),
    "12": ("User-Agent", lambda q: lookup_useragent(q), True),
    "13": ("Discord-Invite", lambda q: core.lookup_discord_invite(q) if hasattr(core, "lookup_discord_invite") else lookup_discord2(q), True),
    "14": ("GitHub-Profil", lambda q: lookup_github(q), True),
    "17": ("Discord-Webhook", lambda q: lookup_discord_webhook(q), True),
    "18": ("Discord-Status", lambda q: lookup_discord_status(), False),
    "19": ("Wetter", lambda q: lookup_weather(q), True),
    "20": ("Wechselkurs", lambda q: lookup_rates(q), True),
    "21": ("Wikipedia", lambda q: lookup_wikipedia(q), True),
    "22": ("YouTube-Info", lambda q: lookup_youtube(q), True),
    "23": ("IP-Netz (RDAP)", lambda q: lookup_ip_network(q), True),
    "24": ("Route (Traceroute)", lambda q: lookup_traceroute(q), True),
    "25": ("Netzwerk (lokal)", lambda q: lookup_network_local(), False),
    "26": ("Snapchat-Profil", lambda q: lookup_snapchat_cli(q), True),
    "27": ("Account-View", lambda q: lookup_account_view_cli(q), True),
    "28": ("Hacker-News", lambda q: lookup_hackernews(), False),
    "29": ("Steam-Check", lambda q: lookup_steam_app(q), True),
    "30": ("GitHub-Repo", lambda q: lookup_github_repo(q), True),
    "31": ("Paket npm/PyPI", lambda q: lookup_package(q), True),
    "32": ("Wayback-Archiv", lambda q: lookup_wayback(q), True),
    "33": ("Bedrohungs-Check", lambda q: lookup_threat_check(q), True),
    "34": ("Aktienkurs", lambda q: lookup_stock(q), True),
    "35": ("NASA-Bild", lambda q: lookup_nasa_apod(), False),
    "36": ("Feiertage", lambda q: lookup_holidays(q), True),
}


# Verlegte Extra-Funktionen (aus v1 uebernommen/angepasst)
def core_or_cli_phone(q):
    return lookup_phone2(q)


def lookup_phone2(query):
    q = query.strip().replace(" ", "").replace("/", "").replace("-", "")
    if q.isdigit() and q.startswith("0"):
        q = "+49" + q[1:]
    if not re.match(r"^\+\d{6,15}$", q):
        return None, "Format: +491711234567 oder 01711234567"
    countries = {
        "+49": "Deutschland", "+43": "Oesterreich", "+41": "Schweiz",
        "+44": "Großbritannien", "+1": "USA / Kanada", "+33": "Frankreich",
        "+39": "Italien", "+34": "Spanien", "+31": "Niederlande",
        "+48": "Polen", "+32": "Belgien", "+353": "Irland",
        "+46": "Schweden", "+45": "Daenemark", "+47": "Norwegen",
        "+358": "Finnland", "+7": "Russland/Kasachstan", "+81": "Japan",
        "+86": "China", "+91": "Indien", "+55": "Brasilien",
        "+61": "Australien", "+64": "Neuseeland", "+27": "Suedafrika",
        "+82": "Suedkorea", "+90": "Tuerkei", "+971": "VAE",
        "+966": "Saudi-Arabien", "+30": "Griechenland", "+351": "Portugal",
        "+36": "Ungarn", "+420": "Tschechien", "+421": "Slowakei",
        "+40": "Rumuenien", "+380": "Ukraine", "+62": "Indonesien",
        "+63": "Philippinen", "+65": "Singapur", "+66": "Thailand",
        "+20": "Aegypten", "+234": "Nigeria", "+254": "Kenia",
    }
    country, plen = "Unbekannt", 0
    for p in sorted(countries, key=len, reverse=True):
        if q.startswith(p):
            country, plen = countries[p], len(p)
            break
    rest = q[plen:]
    hint = "-"
    if q.startswith("+49"):
        if re.match(r"^(15|16|17)", rest):
            hint = c("Mobilfunk-Praefix (DE)", GREEN)
        elif re.match(r"^[2-9]", rest):
            hint = c("Festnetz-Praefix (DE)", CYAN)
    return [
        ("E.164", q),
        ("Landesvorwahl", q[:plen] if plen else "?"),
        ("Vermutliches Land", country),
        ("National", ("0" + rest) if q.startswith("+49") else rest),
        ("Plausibilitaet", hint),
        ("Hinweis", "Ratgeber per Vorwahlen - keine Auskunft zu Personen"),
    ], None


def lookup_mac2(query):
    q = query.strip().lower().replace("-", ":").replace(".", ":")
    if not re.match(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", q):
        return None, "Format: aa:bb:cc:11:22:33"
    vendor = "-"
    try:
        req = urllib.request.Request("https://api.macvendors.com/" + q,
                                     headers=core.UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            vendor = r.read().decode("utf-8", "replace").strip()
    except Exception as e:
        vendor = f"API-Fehler ({type(e).__name__})"
    first = int(q[:2], 16)
    return [
        ("MAC-Adresse", q),
        ("OUI", q[:8]),
        ("Hersteller", vendor),
        ("Multicast-Bit", c("gesetzt", YELLOW) if first & 1 else c("0 (unicast)", GREEN)),
        ("Lokal-Bit", c("lokal verwaltet", YELLOW) if first & 2 else c("global eindeutig", GREEN)),
    ], None


def lookup_discord2(query):
    code = query.strip()
    m = re.search(r"(?:discord\.gg/|discord(?:app)?\.com/invite/)([A-Za-z0-9\-]+)",
                  code, re.I)
    if m:
        code = m.group(1)
    if not re.match(r"^[A-Za-z0-9\-]{2,32}$", code):
        return None, "Format: discord.gg/xyz"
    try:
        d = core.http_json("https://discord.com/api/v10/invites/" + code
                           + "?with_counts=true")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, f"Einladung '{code}' nicht gefunden/abgelaufen"
        if e.code == 429:
            return None, "Discord-Rate-Limit - kurz warten"
        return None, f"Discord API: HTTP {e.code}"
    g = d.get("guild", {})
    levels = {0: "Ungeprueft", 1: "Low (>=5 Min)", 2: "Medium (>=1 Woche)",
              3: "High (>=1 Monat)", 4: "Sehr high (Phone/MFA)"}
    inv = d.get("inviter") or {}
    g = d.get("guild", {}) or {}
    ch = d.get("channel") or {}
    return [
        ("Code", code),
        ("Servername", g.get("name")),
        ("Beschreibung", (g.get("description") or "-")[:60]),
        ("Mitglieder ca.", d.get("approximate_member_count")),
        ("Online ca.", d.get("approximate_presence_count")),
        ("Kanal", f'{ch.get("name", "-")} (Typ {ch.get("type", "?")})'),
        ("Inviter", inv.get("global_name") or inv.get("username") or "-"),
        ("Server erstellt", snowflake_time(g.get("id")) if g.get("id") else "-"),
        ("Verifizierung", levels.get(g.get("verification_level"), "?")),
        ("Features", ", ".join((g.get("features") or [])[:6]) or "-"),
        ("Boost-Stufe", g.get("premium_tier", 0)),
        ("Sprache", g.get("preferred_locale") or "-"),
        ("Vanity-Code", g.get("vanity_url_code") or "-"),
        ("Server-ID", g.get("id")),
    ], None


# ============================== SPECTRE-EXTRA (v2.7: keyless, oeffentlich)
def _spec_json(url, data=None, headers=None, timeout=10):
    """JSON holen (GET/POST) mit Browser-UA - fuer die keyless APIs."""
    h = {"User-Agent": "SPECTRE-Tool/v2.7 (+Nur-Lese-Lookup)"}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        h["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(400000).decode("utf-8", "replace")
    except (ssl.SSLError, ssl.CertificateError, urllib.error.URLError) as e:
        # unvollstaendige Zertifikatskette beim Server: einmal ohne
        # Pruefung wiederholen (gleicher Stoerfall wie im Core)
        low = str(e).lower()
        if "cert" not in low and "ssl" not in low and \
                "self signed" not in low:
            raise
        with urllib.request.urlopen(
                req, timeout=timeout,
                context=ssl._create_unverified_context()) as r:
            raw = r.read(400000).decode("utf-8", "replace")
    return json.loads(raw)


def lookup_hackernews():
    """Top-Storys von Hacker-News (offene Firebase-API, keyless)."""
    try:
        ids = core.http_json(
            "https://hacker-news.firebaseio.com/v0/topstories.json")
    except Exception as e:
        return None, f"HN-API nicht erreichbar ({e})"
    if not isinstance(ids, list) or not ids:
        return None, "keine Stories geliefert"
    from concurrent.futures import ThreadPoolExecutor

    def _item(i):
        try:
            return core.http_json(
                f"https://hacker-news.firebaseio.com/v0/item/{i}.json")
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=6) as ex:
        items = [x for x in ex.map(_item, ids[:8]) if x]
    if not items:
        return None, "Story-Details nicht abrufbar"
    pairs = []
    for n, it in enumerate(items[:7], 1):
        title = str(it.get("title") or "?")[:70]
        url = it.get("url") or (
            f"https://news.ycombinator.com/item?id={it.get('id')}")
        pairs.append((f"{n}. {title}",
                      f"{it.get('score', 0)} Punkte | {str(url)[:75]}"))
    pairs.append(("Quelle", "hacker-news.firebaseio.com (offen, keyless)"))
    return pairs, None


def lookup_steam_app(query):
    """Steam-Store-Suche + App-Details (offene Store-API)."""
    term = query.strip()
    if not term:
        return None, "Spielname eingeben, z.B. 'Hades'"
    try:
        s = _spec_json("https://store.steampowered.com/api/storesearch/"
                       f"?term={_up.quote(term)}&cc=de&l=german")
    except Exception as e:
        return None, f"Steam-Suche fehlgeschlagen ({e})"
    items = s.get("items") or []
    if not items:
        return None, f"Kein Spiel '{term}' gefunden"
    aid = items[0].get("id")
    dd = {}
    for u in (f"https://store.steampowered.com/api/appdetails"
              f"?appids={aid}&cc=de&l=german",
              f"https://store.steampowered.com/api/appdetails?appids={aid}"):
        try:
            d = _spec_json(u, timeout=12)
        except Exception:
            d = {}
        dd = ((d or {}).get(str(aid)) or {}).get("data") or {}
        if dd:
            break
        time.sleep(0.6)
    if not dd:
        # Ehrlicher Teil-Erfolg: Steam sperrt Details manchmal
        # (Ratenlimit/IP-Sperre, z.B. ueber VPN) - Suchtreffer zeigen
        return [
            ("Spiel", items[0].get("name")),
            ("Hinweis", "Details von Steam gesperrt (Ratenlimit oder "
                        "IP-Sperre, z.B. ueber VPN) - nur Suchtreffer"),
            ("Link", f"https://store.steampowered.com/app/{aid}/"),
        ], None
    price = dd.get("price_overview") or {}
    return [
        ("Spiel", dd.get("name") or items[0].get("name")),
        ("Entwickler", ", ".join(dd.get("developers") or []) or "-"),
        ("Preis", price.get("final_formatted") or "-"),
        ("Rabatt", (f"{price.get('discount_percent')} %"
                    if price.get("discount_percent") else "keiner")),
        ("Metacritic", str((dd.get("metacritic") or {}).get("score", "-"))),
        ("Release", (dd.get("release_date") or {}).get("date", "-")),
        ("Genres", ", ".join(g.get("description", "")
                             for g in (dd.get("genres") or [])) or "-"),
        ("Kurz", (dd.get("short_description") or "-")[:220]),
        ("Link", f"https://store.steampowered.com/app/{aid}/"),
    ], None


def lookup_github_repo(query):
    """GitHub-Repository-Statistik (offene API, keyless mit Ratenlimit)."""
    q = query.strip().strip("/")
    if "/" not in q:
        return None, "Format 'owner/repo', z.B. 'torvalds/linux'"
    try:
        d = _spec_json(f"https://api.github.com/repos/{q}",
                       headers={"Accept": "application/vnd.github+json"})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, f"Repo '{q}' nicht gefunden (404)"
        if e.code == 403:
            return None, ("GitHub-Ratenlimit erreicht "
                          "(60 Abfragen/h ohne Token) - spaeter nochmal")
        return None, f"GitHub API: HTTP {e.code}"
    except Exception as e:
        return None, f"GitHub nicht erreichbar ({e})"
    return [
        ("Repo", d.get("full_name")),
        ("Beschreibung", str(d.get("description") or "-")[:220]),
        ("Sprache", d.get("language") or "-"),
        ("Stars", str(d.get("stargazers_count", "-"))),
        ("Forks", str(d.get("forks_count", "-"))),
        ("Offene Issues", str(d.get("open_issues_count", "-"))),
        ("Lizenz", (d.get("license") or {}).get("spdx_id") or "-"),
        ("Archiviert", "ja" if d.get("archived") else "nein"),
        ("Erstellt", str(d.get("created_at", "-"))[:10]),
        ("Letzter Push", str(d.get("pushed_at", "-"))[:10]),
        ("Default-Branch", d.get("default_branch", "-")),
        ("Link", d.get("html_url")),
    ], None


def lookup_package(query):
    """Paket-Info von PyPI oder npm (beide offen und keyless)."""
    name = query.strip()
    if not name:
        return None, "Paketname eingeben, z.B. 'requests' oder 'npm:express'"
    force_npm = name.lower().startswith("npm:")
    if name.lower().startswith("pypi:"):
        name = name[5:]
    if force_npm:
        name = name[4:]
    name = name.strip()
    if not name:
        return None, "Paketname fehlt nach dem Praefix"
    if not force_npm and not name.startswith("@"):
        try:
            d = _spec_json(f"https://pypi.org/pypi/{_up.quote(name)}/json")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                return None, f"PyPI: HTTP {e.code}"
        except Exception as e:
            return None, f"PyPI nicht erreichbar ({e})"
        else:
            info = d.get("info", {})
            rel = ((d.get("releases") or {})
                   .get(info.get("version")) or [])
            uploaded = str(rel[-1].get("upload_time", "-"))[:10] if rel else "-"
            lic = info.get("license") or ""
            if not lic or len(lic) > 60:
                lic = next((c.split("::")[-1].strip()
                            for c in (info.get("classifiers") or [])
                            if c.startswith("License ::")), "-")
            return [
                ("Registry", "PyPI"),
                ("Paket", info.get("name") or name),
                ("Version", info.get("version") or "-"),
                ("Lizenz", str(lic)[:60]),
                ("Autor", str(info.get("author")
                              or info.get("author_email") or "-"))[:60],
                ("Veroeffentlicht", uploaded),
                ("Kurz", str(info.get("summary") or "-")[:200]),
                ("Link", f"https://pypi.org/project/"
                         f"{info.get('name') or name}/"),
            ], None
    try:
        d = _spec_json(f"https://registry.npmjs.org/{_up.quote(name)}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, (f"Paket '{name}' weder auf PyPI noch npm "
                          f"gefunden (404)")
        return None, f"npm-Registry: HTTP {e.code}"
    except Exception as e:
        return None, f"npm-Registry nicht erreichbar ({e})"
    latest = (d.get("dist-tags") or {}).get("latest")
    ver = (d.get("versions") or {}).get(latest) or {}
    auth = ver.get("author")
    if isinstance(auth, dict):
        auth = auth.get("name", "-")
    return [
        ("Registry", "npm"),
        ("Paket", d.get("name") or name),
        ("Version", latest or "-"),
        ("Lizenz", str(ver.get("license") or "-")),
        ("Autor", str(auth or "-"))[:60],
        ("Veroeffentlicht", str((d.get("time") or {}).get(latest, "-"))[:10]),
        ("Kurz", str(d.get("description") or "-")[:200]),
        ("Link", f"https://www.npmjs.com/package/{name}"),
    ], None


def lookup_wayback(query):
    """Wayback-Machine-Abfrage (archive.org, keyless)."""
    q = query.strip()
    if not q:
        return None, "URL oder Domain eingeben, z.B. 'example.com'"
    if "://" not in q:
        q = "https://" + q
    try:
        # Nicht komplett percent-codieren - archive.org liefert dann ein
        # leeres Ergebnis; Strukturzeichen bleiben roh, nur Leerzeichen
        # und Sonderzeichen werden abgesichert.
        d = _spec_json("https://archive.org/wayback/available?url="
                       + _up.quote(q, safe=":/?&=#%"))
    except Exception as e:
        return None, f"archive.org nicht erreichbar ({e})"
    snap = ((d.get("archived_snapshots") or {}).get("closest")) or {}
    if not snap.get("available"):
        return None, "Kein Snapshot bekannt - Seite ist nicht archiviert"
    ts = str(snap.get("timestamp", ""))
    when = (f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}"
            if len(ts) >= 12 else ts)
    return [
        ("Abfrage", q),
        ("Letzter Snapshot", when),
        ("Status", str(snap.get("status", "-"))),
        ("Snapshot-URL", snap.get("url", "-")),
        ("Hinweis", "archive.org speichert oeffentliche Seiten - nur lesen"),
    ], None


def lookup_threat_check(query):
    """Domain gegen OpenPhish-Phishing-Feed und urlscan.io pruefen
    (beide keyless und oeffentlich)."""
    d = query.strip().lower()
    if "://" in d:
        d = d.split("//", 1)[1]
    d = d.split("/")[0].split("@")[-1].split(":")[0].strip(".")
    if not re.match(r"^[a-z0-9\-]+(\.[a-z0-9\-]+)+$", d):
        return None, "Domain eingeben, z.B. example.com"
    # 1) OpenPhish: aktiver Phishing-Feed (plain text, keyless)
    phish = "-"
    try:
        req = urllib.request.Request(
            "https://openphish.com/feed.txt",
            headers={"User-Agent": "SPECTRE-Tool/v2.7"})
        with urllib.request.urlopen(req, timeout=20) as r:
            feed = r.read(4000000).decode("utf-8", "replace")
        hit = False
        for line in feed.splitlines():
            line = line.strip()
            if not line:
                continue
            host = line.split("//")[-1].split("/")[0]
            host = host.split(":")[0].lower()
            if host == d or host.endswith("." + d):
                hit = True
                break
        phish = ("JA - Domain steht im aktiven Phishing-Feed" if hit
                 else "nein - nicht im Feed")
    except Exception as e:
        phish = f"Feed nicht abrufbar ({type(e).__name__})"
    # 2) urlscan.io: letzte Scans der Domain samt Verdikten
    scans, mal = "noch nie gescannt (nicht = sicher)", 0
    try:
        url = ("https://urlscan.io/api/v1/search/?q="
               + _up.quote(f"page.domain:{d}", safe=":")
               + "&size=5")
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "Chrome/126.0 Safari/537.36",
            "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read(400000).decode("utf-8", "replace")
        except (ssl.SSLError, ssl.CertificateError, urllib.error.URLError):
            with urllib.request.urlopen(
                    req, timeout=15,
                    context=ssl._create_unverified_context()) as r:
                raw = r.read(400000).decode("utf-8", "replace")
        js = json.loads(raw)
        results = js.get("results") or []
        if results:
            latest = str(results[0].get("task", {}).get("time", "-"))
            mal = sum(1 for x in results
                      if ((x.get("verdicts") or {}).get("overall") or {})
                      .get("malicious") is True)
            scans = (f"{len(results)} Scans, neuester {latest[:16].replace('T', ' ')}, "
                     f"davon {mal} als boesartig markiert")
        else:
            scans = "noch nie gescannt (nicht = sicher)"
    except urllib.error.HTTPError as e:
        scans = f"urlscan antwortet HTTP {e.code}"
    except Exception as e:
        scans = f"urlscan nicht abrufbar ({type(e).__name__})"
    # 3) Urteil aus beiden Quellen
    if phish.startswith("JA"):
        verdict = "BEDROHUNG: Domain aktiv auf Phishing-Liste"
    elif mal:
        verdict = "BEDROHUNG: urlscan-Scans markieren die Domain"
    elif "nicht abrufbar" in phish or "HTTP" in scans \
            or "nicht abrufbar" in scans:
        verdict = "teilweise nicht pruefbar - Details oben"
    else:
        verdict = "in beiden Quellen kein Treffer"
    return [
        ("Domain", d),
        ("Phishing (OpenPhish)", phish),
        ("Scans (urlscan.io)", scans),
        ("Urteil", verdict),
        ("Hinweis", "kein Treffer heisst NICHT sicher - es werden nur "
                    "oeffentliche Quellen geprueft"),
        ("Quellen", "openphish.com + urlscan.io (keyless)"),
    ], None


def lookup_stock(query):
    """Schlusskurs ueber Yahoo Finance (Browser-UA, keyless, ~15 Min.)."""
    sym = query.strip().upper().replace("$", "").replace(" ", "")
    if not sym:
        return None, "Symbol eingeben, z.B. 'aapl', 'sap' oder 'sap.de'"
    cands = [sym] if "." in sym else [sym, sym + ".DE", sym + ".US"]
    bua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/126.0 Safari/537.36")
    last = "keine Kurse"
    for s in cands:
        try:
            url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
                   + _up.quote(s) + "?interval=1d&range=5d")
            req = urllib.request.Request(url, headers={"User-Agent": bua})
            with urllib.request.urlopen(req, timeout=12) as r:
                d = json.loads(r.read(200000).decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} bei '{s}'"
            continue
        except Exception as e:
            last = str(e)[:80]
            continue
        res = ((d.get("chart") or {}).get("result") or [])
        if not res:
            last = f"'{s}' ohne Daten"
            continue
        m = res[0].get("meta") or {}
        price = m.get("regularMarketPrice")
        prev = m.get("chartPreviousClose") or m.get("previousClose")
        if price is None:
            last = f"'{s}' ohne Kurs"
            continue
        pairs = [
            ("Symbol", str(m.get("symbol") or s)),
            ("Name", str(m.get("shortName") or m.get("longName") or "-")),
            ("Börse", str(m.get("fullExchangeName") or "-")),
            ("Kurs", f"{price:g} {m.get('currency') or ''}".strip()),
        ]
        if prev:
            diff = (price - prev) / prev * 100
            pairs.append(("Vortag", f"{prev:g} ({diff:+.2f} %)"))
        ts = m.get("regularMarketTime")
        pairs.append(("Zeit", datetime.fromtimestamp(ts).strftime(
            "%d.%m.%Y %H:%M") if ts else "-"))
        pairs.append(("Quelle", "Yahoo Finance (kostenlos, "
                                "etwa 15 Min. verzoegert)"))
        return pairs, None
    return None, (f"Symbol '{query}' nicht gefunden - "
                  f"US ohne Suffix, DE z.B. 'sap.de'? ({last})")


def lookup_nasa_apod():
    """Astronomie-Bild des Tages (NASA, DEMO_KEY ohne Registrierung)."""
    try:
        d = _spec_json(
            "https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY"
            "&thumbs=true", timeout=15)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return None, ("NASA-Ratenlimit (DEMO_KEY ~30/h je IP) - "
                          "spaeter nochmal")
        return None, f"NASA API: HTTP {e.code}"
    except Exception as e:
        return None, f"NASA API nicht erreichbar ({e})"
    media = "Video" if d.get("media_type") == "video" else "Bild"
    link = d.get("hdurl") or d.get("url") or d.get("thumbnail_url") or "-"
    return [
        ("Titel", str(d.get("title", "-"))[:100]),
        ("Datum", d.get("date", "-")),
        ("Typ", media),
        ("Erklaerung", str(d.get("explanation") or "-")[:300]),
        ("Link", link),
        ("Bildrechte", str(d.get("copyright", "-"))
         .replace("\n", " ")[:60]),
        ("Quelle", "api.nasa.gov (DEMO_KEY)"),
    ], None


def lookup_holidays(query):
    """Kommende Feiertage nach Laendernummer (date.nager.at, keyless)."""
    from datetime import date as _date
    cc = (query.strip() or "DE").upper()[:2]
    if not re.match(r"^[A-Z]{2}$", cc):
        return None, "Laendernummer eingeben, z.B. DE, AT, CH, FR, US"
    today = _date.today()
    entries = []
    for year in (today.year, today.year + 1):
        try:
            d = _spec_json(
                f"https://date.nager.at/api/v3/PublicHolidays/{year}/{cc}")
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None, f"Laendernummer '{cc}' nicht bekannt"
            return None, f"Feiertage-API: HTTP {e.code}"
        except Exception as e:
            return None, f"Feiertage-API nicht erreichbar ({e})"
        if not isinstance(d, list):
            return None, f"Feiertage-API: unerwartete Antwort fuer {cc}"
        entries.extend(d)
    upcoming = [h for h in entries
                if str(h.get("date", "")) >= today.isoformat()][:8]
    if not upcoming:
        return None, "keine kommenden Feiertage gefunden"
    land = (upcoming[0].get("globalName")
            or upcoming[0].get("englishName") or cc)
    pairs = [("Land", f"{cc} - {land}")]
    for h in upcoming:
        pairs.append((str(h.get("date")),
                      str(h.get("localName") or h.get("name"))))
    pairs.append(("Quelle", "date.nager.at (keyless)"))
    return pairs, None


def send_webhook_message(url, text, count=1):
    """Freie Nachricht per eigenem Discord-Webhook senden (eigener Server).
    count > 1 = dieselbe Nachricht mehrfach (max 1000): kein kuenstliches
    Warten - bei HTTP 429 wird retry_after ausgesetzt (bis 3x pro
    Nachricht), danach sofort weiter; effektiv volles Discord-Tempo
    (ca. 5 Nachrichten alle 5 s pro Kanal)."""
    url = url.strip()
    if not url.startswith("https://"):
        return None, "Webhook-URL muss mit https:// beginnen"
    if "discord.com/api/webhooks" not in url and \
            "discordapp.com/api/webhooks" not in url:
        return None, "Keine Discord-Webhook-URL (…/api/webhooks/…)"
    try:
        count = max(1, min(int(count or 1), 1000))
    except (TypeError, ValueError):
        count = 1
    payload = json.dumps({"content": text[:1900]}).encode("utf-8")
    sent = 0
    errs = 0
    last_err = "-"
    for i in range(count):
        for attempt in (1, 2, 3):
            req = urllib.request.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "User-Agent": "SPECTRE-Tool/v2.7"})
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    code = r.status
                if code in (200, 204):
                    sent += 1
                    break
                last_err = f"HTTP {code}"
                errs += 1
                break
            except urllib.error.HTTPError as e:
                if e.code == 404 and sent == 0 and errs == 0:
                    return None, "Webhook nicht mehr gueltig (404)"
                if e.code == 429 and attempt < 3:
                    try:
                        wait = float(json.loads(e.read().decode())
                                     .get("retry_after") or 1)
                    except Exception:
                        wait = 1.0
                    time.sleep(min(max(wait, 0.3), 8.0))
                    continue
                last_err = f"HTTP {e.code}"
                errs += 1
                break
            except Exception as e:
                last_err = str(e)[:70]
                errs += 1
                break
        if i < count - 1:
            time.sleep(0.05)   # Tempo: 429-Handling drosselt selbst
    if sent:
        wid = url.split("/api/webhooks/")[1].split("/")[0]
        pairs = [
            ("Status", f"{sent}/{count} Nachrichten gesendet"),
            ("Webhook-ID", wid),
            ("Hinweis", "nur eigene Nachrichten - kein Versand ueber "
                        "fremde Webhooks"),
        ]
        if errs:
            pairs.append(("Fehler", f"{errs}x {last_err}"))
        if sent < count:
            pairs.append(("Ratenlimit", "Discord drosselt - weniger "
                                        "oder spaeter nochmal"))
        return pairs, None
    return None, f"Senden fehlgeschlagen ({count} Versuche): {last_err}"


def run_discord_bot():
    """Eigenen Discord-Bot starten (Token aus dem Developer Portal)."""
    try:
        import discord_bot
    except Exception as e:
        err(f"Bot-Modul nicht ladbar ({e})")
        info("discord.py pruefen: pip install discord.py")
        return
    try:
        discord_bot.run()
    except KeyboardInterrupt:
        print()
        info("Bot-Modul beendet - zurueck im Menue")


def main():
    show_start_banner()
    while True:
        show_menu()
        try:
            choice = input(f"   {YELLOW}Wahl ▸ {R}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(f"\n   {GRAY}Abbruch.{R}\n")
            break
        if choice == "":
            continue
        if choice in ("m", "matrix"):
            matrix_live()
            time.sleep(0.15)
            continue
        if choice in ("b", "bot"):
            run_discord_bot()
            time.sleep(0.15)
            continue
        if choice == "0":
            animate_exit()
            break
        if choice.startswith("info"):
            nr = choice.split()[1] if len(choice.split()) > 1 else ""
            if nr in DESC:
                print(f"\n   {CYAN}[{nr}] {WHITE}{dict(MENU_ITEMS)[nr]}{R}")
                print(f"   {GRAY}{DESC[nr]}{R}")
            else:
                err("info <Nr.> nutzen, z.B. 'info 9'")
            continue
        if choice == "15":
            text = read_multiline()
            if not text:
                err("kein Header eingefuegt - abgebrochen")
                continue
            run_lookup("E-Mail-Header-Analyse", analyze_email_header, text)
            time.sleep(0.15)
            continue
        if choice == "16":
            run_lookup("Meine IP", lookup_my_ip_links)
            try:
                ask = input(f"   {YELLOW}Browser mit ipinfo.io oeffnen? (j/N): {R}").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ask = ""
            if ask in ("j", "y", "ja"):
                try:
                    os.startfile("https://ipinfo.io")
                    info("Browser geoeffnet - dort siehst du IP, Stadt, ISP, ASN")
                except Exception as e:
                    err(f"Konnte Browser nicht oeffnen ({e})")
                    info("Link manuell oeffnen: https://ipinfo.io")
            time.sleep(0.15)
            continue
        if choice == "1":
            q = prompt("IP eingeben (z.B. 8.8.8.8)")
            if not q:
                err("keine Eingabe - abgebrochen")
                continue
            run_lookup("IP & Geo-Karte", lookup_ip_full, q)
            if _LAST_GEO:
                print_geo_map(_LAST_GEO)
                try:
                    ask = input(f"   {YELLOW}Karte oeffnen? (o)SM "
                                f"(g)Google (n)ein: {R}").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ask = ""
                glat, glon = _LAST_GEO["lat"], _LAST_GEO["lon"]
                if ask in ("o", "osm", "j", "y", "ja"):
                    url = (f"https://www.openstreetmap.org/?mlat={glat}"
                           f"&mlon={glon}#map=11/{glat}/{glon}")
                    try:
                        os.startfile(url)
                        info(f"OpenStreetMap geoeffnet - Ziel: "
                             f"{_LAST_GEO.get('city') or _LAST_GEO['ip']}")
                    except Exception as e:
                        err(f"Browser nicht moeglich ({e})")
                        info(f"Link: {url}")
                elif ask in ("g", "google"):
                    url = f"https://www.google.com/maps?q={glat},{glon}"
                    try:
                        os.startfile(url)
                        info("Google Maps geoeffnet")
                    except Exception as e:
                        err(f"Browser nicht moeglich ({e})")
                        info(f"Link: {url}")
            time.sleep(0.15)
            continue
        if choice == "37":
            url = prompt("Discord-Webhook-URL")
            if not url:
                err("keine URL - abgebrochen")
                continue
            txt = prompt("Nachricht")
            if not txt:
                err("kein Text - abgebrochen")
                continue
            n_in = prompt("Wie oft senden (1 = einmal, max 1000)")
            m = re.search(r"\d+", n_in or "")
            n = max(1, min(int(m.group()) if m else 1, 1000))
            run_lookup("Discord senden", send_webhook_message, url, txt, n)
            time.sleep(0.15)
            continue
        if choice not in MENU_ACTIONS:
            err(f"Ungueltige Wahl - 0-{len(MENU_ITEMS)} oder 'info Nr.'")
            continue
        label, fn, needs_input = MENU_ACTIONS[choice]
        q = ""
        if needs_input:
            q = prompt(f"Eingabe fuer [{choice}] {label} (info {choice} = Hilfe)")
            if not q:
                err("keine Eingabe - abgebrochen")
                continue
        run_lookup(label, fn, q, raw=False)
        time.sleep(0.15)


if __name__ == "__main__":
    main()
