# -*- coding: utf-8 -*-
"""
SPECTRE Bot-Terminal - alles ueber die Tastatur:
  SPAM: Text / Links / BILDER / Mix in jeden Kanal + aktive Threads
  Server (Name/Icon/Beschreibung), Kanaele (Name/Slowmode),
  Rollen (Name/Farbe), NUKE, Mitglieder (Liste/Suche/Nick/Kick), Status.
Verbindet sich mit dem Bot-Token aus bot_config.json (nur eigener Server).

Regeln: Deckel 1000 Nachrichten pro Lauf, Strg+C stoppt sofort,
NUKE braucht Servername + das Wort LOESCHEN, ALLE-KICK braucht "KICK".
Owner-Kick ist von Discord gesperrt (Tool sagt das ehrlich).
Backups liegen in LookupTool/backups (Doku - kein Undo).
Start: Doppelklick "SPECTRE Terminal" oder python bot_cli.py
"""
import asyncio
import os
import queue
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import discord

from server_panel import (API, BACKUP_DIR, PanelClient, load_token, ts)

MAX_TOTAL = 1000
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MAX_FILES = 10          # Discord-Limit pro Nachricht
MAX_SIZE = 25 * 1024 * 1024
POSTABLE = (discord.ChannelType.text, discord.ChannelType.news)

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
CYAN, GRAY, RED = "\x1b[96m", "\x1b[90m", "\x1b[91m"
YELLOW, WHITE = "\x1b[96m", "\x1b[97m"


def info(msg):
    print(f"   {CYAN}{msg}{R}", flush=True)


def note(msg):
    print(f"   {GRAY}{msg}{R}", flush=True)


def err(msg):
    print(f"   {RED}{msg}{R}", flush=True)


BANNER = [
    r"    ☠ ☠ ☠ ☠ ☠ ☠ ☠ ☠ ☠ ☠ ☠ ☠",
    r"   ███████╗██████╗ ███████╗ ██████╗████████╗██████╗ ███████╗",
    r"   ██╔════╝██╔══██╗██╔════╝██╔════╝╚══██╔══╝██╔══██╗██╔════╝",
    r"   ███████╗██████╔╝█████╗  ██║        ██║   ██████╔╝█████╗  ",
    r"   ╚════██║██╔═══╝ ██╔══╝  ██║        ██║   ██╔══██║██╔══╝  ",
    r"   ███████║██║     ███████╗╚██████╗   ██║   ██║  ██║███████╗",
    r"   ╚══════╝╚═╝     ╚══════╝ ╚═════╝  ╚═╝   ╚═╝  ╚═╝╚══════╝",
    r"          B O T - T E R M I N A L   v1.0",
]


def show_banner():
    print(f"{CYAN}{BOLD}", flush=True)
    for line in BANNER:
        print("   " + line, flush=True)
    print(f"{R}", flush=True)


# ---------------------------------------------------------------- Helfer
async def ainput(prompt):
    return await asyncio.to_thread(input, prompt)


def parse_selection(text, count):
    """'1,3,5-8' -> [1,3,5,6,7,8] (auf count begrenzt)."""
    out = []
    for part in [x.strip() for x in text.replace(";", ",").split(",")
                 if x.strip()]:
        if "-" in part:
            a, _, b = part.partition("-")
            try:
                a, b = int(a), int(b)
            except ValueError:
                continue
            out += list(range(min(a, b), max(a, b) + 1))
        else:
            try:
                out.append(int(part))
            except ValueError:
                continue
    return sorted({i for i in out if 1 <= i <= count})


def parse_files(inp):
    """Pfade (mit ; getrennt) oder Ordner -> Bildliste + Warnungen."""
    files, warns = [], []
    for part in [x.strip().strip('"') for x in inp.split(";") if x.strip()]:
        if os.path.isdir(part):
            found = sorted(
                os.path.join(part, f) for f in os.listdir(part)
                if os.path.splitext(f)[1].lower() in IMG_EXT)
            if not found:
                warns.append("keine Bilder in " + part)
            files += found
        elif os.path.isfile(part):
            if os.path.splitext(part)[1].lower() in IMG_EXT:
                files.append(part)
            else:
                warns.append("kein Bild-Format: " + part)
        else:
            warns.append("nicht gefunden: " + part)
    kept = []
    for f in files:
        try:
            size = os.path.getsize(f)
        except OSError:
            warns.append("nicht lesbar: " + os.path.basename(f))
            continue
        if size > MAX_SIZE:
            warns.append("zu gross (>25MB): " + os.path.basename(f))
            continue
        if size == 0:
            warns.append("leer: " + os.path.basename(f))
            continue
        kept.append(f)
    return kept, warns


def prepare_icon(path):
    """Bild fuers Server-Icon: max. 512px, Ziel <=256KB -> Bytes (PIL)."""
    import io
    try:
        from PIL import Image
    except Exception:
        with open(path, "rb") as f:
            data = f.read()
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Bild zu gross (>8MB) und PIL fehlt")
        return data
    im = Image.open(path)
    if getattr(im, "n_frames", 1) > 1:      # GIF: erstes Frame
        im.seek(0)
    im = im.convert("RGBA")
    im.thumbnail((512, 512))
    limit = 256 * 1024
    buf = io.BytesIO()
    im.save(buf, "PNG")
    if buf.tell() <= limit:
        return buf.getvalue()
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.split()[-1])
    for q in (85, 70, 55, 40, 30):
        buf = io.BytesIO()
        bg.save(buf, "JPEG", quality=q)
        if buf.tell() <= limit:
            return buf.getvalue()
    return buf.getvalue()                    # letzter Versuch - API entscheidet


# ---------------------------------------------------------------- Client
class TermClient(PanelClient):
    """PanelClient + Spam mit Text/Links/Bildern fuers Terminal."""

    def __init__(self, events, selftest=False, test_spam=False):
        super().__init__(events, selftest=selftest)
        self.test_spam = test_spam
        self.stats = {"sent": 0, "err": 0}

    def list_targets(self, mode):
        """kanaele|threads|alle -> ([(id,label)], anzahl_ohne_recht)."""
        g = self.guilds[0] if self.guilds else None
        if g is None:
            return [], 0
        kanaele, threads, locked = [], [], 0

        def has_access(ch):
            try:
                p = ch.permissions_for(g.me)
                return bool(p.view_channel and p.send_messages)
            except Exception:
                return False

        for ch in g.channels:
            if isinstance(ch, discord.CategoryChannel):
                continue
            if ch.type not in POSTABLE:
                continue
            if not has_access(ch):
                locked += 1
                continue
            mark = ("\U0001f4ac" if ch.type == discord.ChannelType.text
                    else "\U0001f4e2")
            par = " (%s)" % ch.category.name if ch.category else ""
            kanaele.append((ch.id, "%s #%s%s" % (mark, ch.name, par)))
        for th in g.threads:
            if not has_access(th):
                locked += 1
                continue
            par = th.parent.name if th.parent else "?"
            threads.append((th.id, "\U0001f9f5 %s (in #%s)" % (th.name, par)))
        if mode == "threads":
            return threads, locked
        if mode == "alle":
            return kanaele + threads, locked
        return kanaele, locked

    async def run_spam(self, targets, content, files, rounds, delay):
        self.stop_flag = False
        total = max(len(targets) * rounds, 1)
        sent = err = 0
        self.emit("prog", 0, total, "starte ...")
        for cid, label in targets:
            if self.stop_flag:
                break
            try:
                ch = self.get_channel(cid) or await self.fetch_channel(cid)
            except Exception as e:
                err += 1
                self.stats["err"] += 1
                self.emit("log", "Ziel weg: %s (%s)" % (label, str(e)[:60]))
                continue
            for _ in range(rounds):
                if self.stop_flag:
                    break
                try:
                    kw = {"files": [discord.File(p) for p in files]} if files else {}
                    await ch.send(content if content else None, **kw)
                    sent += 1
                    self.stats["sent"] += 1
                    self.emit("prog", sent, total, label)
                except discord.Forbidden:
                    err += 1
                    self.stats["err"] += 1
                    self.emit("log", "KEIN-RECHT(403): %s" % label)
                    break
                except discord.HTTPException as e:
                    err += 1
                    self.stats["err"] += 1
                    if e.status == 413:
                        self.emit("log", "Datei zu gross (413): %s" % label)
                    else:
                        self.emit("log", "HTTP%d %s: %s"
                                  % (e.status, label, str(e)[:60]))
                    break
                except Exception as e:
                    err += 1
                    self.stats["err"] += 1
                    self.emit("log", "Fehler %s: %s" % (label, str(e)[:70]))
                    break
                if delay > 0:
                    await asyncio.sleep(delay)
        self.emit("done", "spam", sent, err)

    # ---------------- Mitglieder-Nicknames ----------------
    async def run_setnick(self, pairs, pattern):
        """pairs: [(id, name)]. Platzhalter: {n} = Nummer, {user} = Name."""
        g = self.guilds[0]
        self.stop_flag = False
        total = len(pairs)
        sent = err = 0
        gekuerzt = False
        self.emit("prog", 0, total, "setze Nicknames ...")
        for i, (mid, name) in enumerate(pairs, 1):
            if self.stop_flag:
                break
            nick = pattern.replace("{n}", str(i)).replace("{user}", name)
            if len(nick) > 32:
                nick = nick[:32]             # Discord-Limit Nick = 32
                if not gekuerzt:
                    gekuerzt = True
                    self.emit("log", "Nickname-Text auf 32 Zeichen gekuerzt")
            if str(mid) == str(self.user.id):
                # eigener Eintrag: nur /members/@me akzeptiert das (403 sonst)
                url = "%s/guilds/%d/members/@me" % (API, g.id)
            else:
                url = "%s/guilds/%d/members/%s" % (API, g.id, mid)
            st, body = await self._session_patch(url, {"nick": nick})
            if st in (200, 204):
                sent += 1
                self.emit("prog", sent, total, "%s -> %s" % (name, nick))
            else:
                err += 1
                if st == 403:
                    self.emit("log", "KEIN-RECHT/Hierarchie(403): %s" % name)
                elif st == 400:
                    self.emit("log", "HTTP400 %s: %s"
                              % (name, str(body)[:70]))
                else:
                    self.emit("log", "Nick HTTP%d %s: %s"
                              % (st, name, str(body)[:70]))
            await asyncio.sleep(0.05)
        self.emit("done", "nick", sent, err)

    # ---------------- Kanal / Rolle / Server ----------------
    async def run_slowmode(self, ch_ids, seconds):
        self.stop_flag = False
        total = len(ch_ids)
        sent = err = 0
        self.emit("prog", 0, total, "setze Slowmode ...")
        for cid in ch_ids:
            if self.stop_flag:
                break
            try:
                ch = self.get_channel(cid) or await self.fetch_channel(cid)
                await ch.edit(rate_limit_per_user=seconds)
                sent += 1
                self.emit("prog", sent, total, ch.name)
            except discord.Forbidden:
                err += 1
                self.emit("log", "KEIN-RECHT(403): Kanal %s" % cid)
            except Exception as e:
                err += 1
                self.emit("log", "Slowmode %s: %s" % (cid, str(e)[:80]))
        self.emit("done", "slowmode", sent, err)

    async def run_role_color(self, role_ids, hexstr):
        g = self.guilds[0]
        self.stop_flag = False
        try:
            h = hexstr.strip().lstrip("#")
            if len(h) == 3:
                h = "".join(x * 2 for x in h)
            if len(h) != 6:
                raise ValueError("Laenge")
            colour = discord.Colour(int(h, 16))
        except Exception:
            self.emit("log", "Farbe ungueltig - z.B. ff0000 oder #00aaff")
            self.emit("done", "farbe", 0, 1)
            return
        total = len(role_ids)
        sent = err = 0
        self.emit("prog", 0, total, "setze Farben ...")
        for rid in role_ids:
            if self.stop_flag:
                break
            r = g.get_role(rid)
            if r is None:
                err += 1
                continue
            if r.managed:
                err += 1
                self.emit("log", "uebersprungen (managed): %s" % r.name)
                continue
            try:
                await r.edit(colour=colour)
                sent += 1
                self.emit("prog", sent, total, r.name)
            except discord.Forbidden:
                err += 1
                self.emit("log", "KEIN-RECHT(403): Rolle %s" % r.name)
            except Exception as e:
                err += 1
                self.emit("log", "Farbe %s: %s" % (r.name, str(e)[:70]))
        self.emit("done", "farbe", sent, err)

    async def _backup_icon(self, g):
        """Sichert das aktuelle Server-Icon nach backups/ (best effort)."""
        try:
            url = g.icon_url
            if not url:
                return
            async with self.my_session.get(str(url)) as r:
                if r.status != 200:
                    return
                raw = await r.read()
            os.makedirs(BACKUP_DIR, exist_ok=True)
            ext = os.path.splitext(str(url).split("?")[0])[1] or ".png"
            p = os.path.join(BACKUP_DIR, "server_icon_alt_%s%s" % (ts(), ext))
            with open(p, "wb") as f:
                f.write(raw)
            self.emit("log", "altes Icon gesichert: " + os.path.basename(p))
        except Exception:
            self.emit("log", "altes Icon nicht gesichert (Weiter geht trotzdem)")

    async def set_icon(self, path):
        """path=None -> Icon entfernen. Sonst Datei vorbereiten + setzen."""
        g = self.guilds[0]
        try:
            await self._backup_icon(g)
            if path is None:
                await g.edit(icon=None)
                self.emit("log", "Server-Icon entfernt")
                self.emit("done", "icon", 1, 0)
                return
            data = prepare_icon(path)
            await g.edit(icon=data)
            self.emit("log", "Server-Icon gesetzt (%d KB)"
                      % (len(data) // 1024))
            self.emit("done", "icon", 1, 0)
        except Exception as e:
            self.emit("log", "Icon-Fehler: %s" % str(e)[:140])
            self.emit("done", "icon", 0, 1)

    async def set_description(self, text):
        g = self.guilds[0]
        try:
            val = (text or "").strip()
            gekuerzt = False
            if len(val) > 120:
                val = val[:120]
                gekuerzt = True
            if gekuerzt:
                self.emit("log", "Beschreibung auf 120 Zeichen gekuerzt "
                                 "(Discord-Limit)")
            await g.edit(description=val or None)
            if val:
                self.emit("log", "Server-Beschreibung gesetzt: %r" % val)
            else:
                self.emit("log", "Server-Beschreibung entfernt")
            self.emit("done", "beschreibung", 1, 0)
        except Exception as e:
            self.emit("log", "Beschreibung-Fehler: %s" % str(e)[:140])
            self.emit("done", "beschreibung", 0, 1)

    async def _selftest(self, data):
        if not self.test_spam:
            await super()._selftest(data)
            return
        if "error" in data:
            print("SELFTEST_FEHLER:", data["error"], flush=True)
            await self.close()
            return
        print("ANGEMELDET:", data["user"], flush=True)
        print("SERVER:", data["guild"], "| MEMBER:", data["members"], flush=True)
        targets, locked = self.list_targets("kanaele")
        print("SEND-BAR:", len(targets), "| ohne Recht:", locked, flush=True)
        if not targets:
            print("KEIN_ZIEL", flush=True)
            await self.close()
            return
        img = None
        for cand in (
                r"C:\Users\mavwi\AppData\Local\Temp\opencode\pfp_final.jpg",
                os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "testbild.png")):
            if os.path.isfile(cand):
                img = cand
                break
        cid, label = targets[0]
        try:
            ch = self.get_channel(cid) or await self.fetch_channel(cid)
            kw = {"files": [discord.File(img)]} if img else {}
            await ch.send("SPECTRE Bot-Terminal Test "
                          "(Text + Link https://discord.com)", **kw)
            print("TEST-SPAM: OK in", label, "| Bild:",
                  os.path.basename(img) if img else "keines", flush=True)
        except Exception as e:
            print("TEST-SPAM: FEHLER in", label, type(e).__name__,
                  str(e)[:140], flush=True)
        print("SELFTEST_OK", flush=True)
        await self.close()


# ---------------------------------------------------------------- Laeufe
def render_ev(ev, st):
    kind = ev[0]
    if kind == "log":
        if st["open"]:
            print(flush=True)
            st["open"] = False
        note("· " + ev[1])
    elif kind == "prog":
        _, sent, total, label = ev
        st["open"] = True
        sys.stdout.write("\r   %s[%d/%d]%s %-46.46s"
                         % (CYAN, sent, total, R, label))
        sys.stdout.flush()
    elif kind == "done":
        if st["open"]:
            print(flush=True)
            st["open"] = False
        info("FERTIG [%s]: %d ok, %d Fehler" % (ev[1], ev[2], ev[3]))


async def run_op(client, coro):
    """Operation ausfuehren und Events live ausgeben -> done-Event/None."""
    st = {"open": False}
    task = asyncio.ensure_future(coro)
    last = None
    while not task.done():
        try:
            ev = client.events.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.05)
            continue
        render_ev(ev, st)
        if ev[0] == "done":
            last = ev
    while True:
        try:
            ev = client.events.get_nowait()
        except queue.Empty:
            break
        render_ev(ev, st)
        if ev[0] == "done":
            last = ev
    if st["open"]:
        print(flush=True)
    try:
        task.result()
    except Exception as e:
        err("Lauf fehlgeschlagen: %s" % str(e)[:120])
        return None
    return last


# ---------------------------------------------------------------- Aktionen
async def pick_targets(client):
    print("   [1] alle sendbaren Kanäle   [2] Kanäle + aktive Threads")
    print("   [3] nur Threads             [4] Auswahl eingeben")
    z = (await ainput("   %sZiel ▸ %s" % (YELLOW, R))).strip() or "1"
    mode = {"1": "kanaele", "2": "alle", "3": "threads"}.get(z, "kanaele")
    if z == "4":
        all_t, locked = client.list_targets("alle")
        if locked:
            note("%d Kanäle/Threads ohne Recht (nicht gelistet)" % locked)
        if not all_t:
            err("keine Ziele")
            return []
        for i, (_, lab) in enumerate(all_t, 1):
            print("   %3d> %s" % (i, lab))
        sel = (await ainput("   %sAuswahl (z.B. 1,3,5-8) ▸ %s"
                            % (YELLOW, R))).strip()
        idx = parse_selection(sel, len(all_t))
        return [all_t[i - 1] for i in idx]
    targets, locked = client.list_targets(mode)
    if locked:
        note("%d Kanäle/Threads ohne Recht übersprungen" % locked)
    return targets


async def ask_text(prompt_hint):
    print(prompt_hint)
    lines = []
    while True:
        line = await ainput("   | ")
        if line == "":
            break
        lines.append(line)
    return lines


async def do_spam(client, kind):
    """kind: text | link | bild | mix"""
    title = {"text": "TEXT", "link": "TEXT + LINKS", "bild": "BILDER",
             "mix": "MIX (Text + Links + Bilder)"}[kind]
    info("SPAM: " + title)
    targets = await pick_targets(client)
    if not targets:
        err("keine Ziele - abgebrochen")
        return
    lines = []
    if kind == "bild":
        lines = await ask_text("Nachricht optional (leere Zeile = nur "
                               "Bilder, mehrere Zeilen ok):")
    else:
        lines = await ask_text("Nachricht (mehrere Zeilen, leere Zeile "
                               "beendet):")
    if kind == "link":
        links = (await ainput("   %sLinks (mit ; getrennt) ▸ %s"
                              % (YELLOW, R))).strip()
        lines += [x.strip() for x in links.split(";") if x.strip()]
    elif kind == "mix":
        links = (await ainput("   Links optional (mit ; getrennt, "
                              "Enter=keine) ▸ ")).strip()
        if links:
            lines += [x.strip() for x in links.split(";") if x.strip()]
    files = []
    if kind in ("bild", "mix"):
        inp = (await ainput("   %sBilder: Pfade (mit ; ) oder Ordner ▸ %s"
                            % (YELLOW, R))).strip()
        files, warns = parse_files(inp)
        for w in warns:
            err(w)
        if len(files) > MAX_FILES:
            note("max %d Bilder pro Nachricht - nehme die ersten %d"
                 % (MAX_FILES, MAX_FILES))
            files = files[:MAX_FILES]
    content = "\n".join(lines)
    if not content.strip() and not files:
        err("nichts zum Senden (Text oder Bilder nötig)")
        return
    rounds_in = (await ainput("   Runden pro Kanal [1]: ")).strip()
    try:
        rounds = max(1, min(500, int(rounds_in or "1")))
    except ValueError:
        rounds = 1
    delay_in = (await ainput("   Delay in Sekunden [0.0]: ")).strip()
    try:
        delay = max(0.0, min(60.0, float(delay_in or "0")))
    except ValueError:
        delay = 0.0
    planned = len(targets) * rounds
    if planned > MAX_TOTAL:
        rounds = max(1, MAX_TOTAL // len(targets))
        planned = len(targets) * rounds
        note("Deckel 1000: Runden auf %d reduziert -> %d Nachrichten"
             % (rounds, planned))
    info("Plan: %d Ziele x %d = %d Nachrichten%s | Discord bremst selbst"
         % (len(targets), rounds, planned,
            (" + %d Bild(er)" % len(files)) if files else ""))
    sure = (await ainput("   %sStarten? [Enter=ja, n=nein] ▸ %s"
                         % (YELLOW, R))).strip().lower()
    if sure in ("n", "nein", "q", "x"):
        note("abgebrochen")
        return
    await run_op(client, client.run_spam(targets, content, files,
                                         rounds, delay))


async def do_targets_view(client):
    targets, locked = client.list_targets("alle")
    info("Ziele: %d sendbar" % len(targets))
    for i, (_, lab) in enumerate(targets, 1):
        print("   %3d> %s" % (i, lab))
    if locked:
        note("%d ohne Recht (nicht sendbar)" % locked)


async def do_server_name(client):
    data = client._status()
    akt = data.get("guild", "?")
    neu = (await ainput("   Server-Name (aktuell «%s», Enter=nein) ▸ "
                        % akt)).strip()
    if not neu:
        note("abgebrochen")
        return
    await run_op(client, client.set_server_name(neu))


async def do_rename_channels(client):
    data = client._status()
    chans = data.get("channels", [])
    if not chans:
        err("keine Kanäle")
        return
    for i, c in enumerate(chans, 1):
        print("   %3d> %s" % (i, c["label"]))
    sel = (await ainput("   Auswahl ('alle' oder z.B. 1,3,5-8) ▸ ")).strip()
    if sel.lower() in ("alle", "a", "*"):
        ids = [c["id"] for c in chans]
    else:
        idx = parse_selection(sel, len(chans))
        ids = [chans[i - 1]["id"] for i in idx]
    if not ids:
        err("keine Auswahl - abgebrochen")
        return
    name = (await ainput("   Neuer Kanalname: ")).strip()
    if not name:
        err("kein Name - abgebrochen")
        return
    info("benenne %d Einträge -> %r" % (len(ids), name))
    await run_op(client, client.run_rename_channels(ids, name))


async def do_rename_roles(client):
    data = client._status()
    roles = data.get("roles", [])
    if not roles:
        err("keine Rollen")
        return
    for i, r in enumerate(roles, 1):
        print("   %3d> %s" % (i, r["label"]))
    sel = (await ainput("   Auswahl ('alle' = nur editierbare) ▸ ")).strip()
    if sel.lower() in ("alle", "a", "*"):
        ids = [r["id"] for r in roles if r["editable"]]
        skip = len(roles) - len(ids)
        if skip:
            note("%d nicht editierbare Rollen übersprungen" % skip)
    else:
        idx = parse_selection(sel, len(roles))
        ids = [roles[i - 1]["id"] for i in idx]
        ids = [i for i in ids
               if next(r["editable"] for r in roles if r["id"] == i)]
    if not ids:
        err("keine editierbaren Rollen gewählt - abgebrochen")
        return
    name = (await ainput("   Neuer Rollenname: ")).strip()
    if not name:
        err("kein Name - abgebrochen")
        return
    info("benenne %d Rollen -> %r" % (len(ids), name))
    await run_op(client, client.run_rename_roles(ids, name))


# ---------------------------------------------------------------- Unter-Menues
async def menu_server(client):
    while True:
        print("   [1] Server-Name    [2] Icon setzen (Bild von der Platte)")
        print("   [3] Icon entfernen  [4] Beschreibung (Enter = weg)")
        print("   [0] zurück")
        w = (await ainput("   %sServer ▸ %s" % (YELLOW, R))).strip()
        if w == "0":
            return
        if w == "1":
            await do_server_name(client)
        elif w == "2":
            p = (await ainput("   Bildpfad ▸ ")).strip().strip('"')
            if not p or not os.path.isfile(p):
                err("Datei nicht gefunden")
                continue
            note("altes Icon wird zuerst nach backups/ gesichert")
            info("setze Server-Icon: " + os.path.basename(p))
            await run_op(client, client.set_icon(p))
        elif w == "3":
            sure = (await ainput("   %sWirklich Icon entfernen? "
                                 "[ja/Enter=nein] ▸ %s" % (RED, R)
                                 )).strip().lower()
            if sure in ("ja", "j", "yes"):
                await run_op(client, client.set_icon(None))
            else:
                note("abgebrochen")
        elif w == "4":
            t = (await ainput("   Beschreibung (Enter = entfernen) ▸ "
                              )).strip()
            sure = (await ainput("   %sAnwenden? [ja/Enter=nein] ▸ %s"
                                 % (YELLOW, R))).strip().lower()
            if sure in ("ja", "j", "yes"):
                await run_op(client, client.set_description(t))
            else:
                note("abgebrochen")
        else:
            note("unbekannte Wahl")
        print()


async def menu_channels(client):
    while True:
        print("   [1] Kanäle umbenennen    [2] Slowmode (Sperre) setzen")
        print("   [0] zurück")
        w = (await ainput("   %sKanäle ▸ %s" % (YELLOW, R))).strip()
        if w == "0":
            return
        if w == "1":
            await do_rename_channels(client)
        elif w == "2":
            data = client._status()
            chans = [c for c in data.get("channels", [])
                     if c["kind"] == "kanal" and c.get("sendable")]
            if not chans:
                err("keine sendbaren Kanäle")
                continue
            for i, c in enumerate(chans, 1):
                print("   %3d> %s" % (i, c["label"]))
            sel = (await ainput("   Auswahl ('alle' oder z.B. 1,3,5-8) ▸ "
                                )).strip()
            if sel.lower() in ("alle", "a", "*"):
                ids = [c["id"] for c in chans]
            else:
                ids = [chans[i - 1]["id"]
                       for i in parse_selection(sel, len(chans))]
            if not ids:
                err("keine Auswahl - abgebrochen")
                continue
            s = (await ainput("   Sekunden (0 = aus, max 21600) ▸ ")).strip()
            try:
                secs = max(0, min(21600, int(s or "0")))
            except ValueError:
                secs = 0
            info("Slowmode %ds in %d Kanälen" % (secs, len(ids)))
            await run_op(client, client.run_slowmode(ids, secs))
        else:
            note("unbekannte Wahl")
        print()


async def menu_roles(client):
    while True:
        print("   [1] Rollen umbenennen     [2] Rollen-Farbe setzen")
        print("   [0] zurück")
        w = (await ainput("   %sRollen ▸ %s" % (YELLOW, R))).strip()
        if w == "0":
            return
        if w == "1":
            await do_rename_roles(client)
        elif w == "2":
            data = client._status()
            roles = data.get("roles", [])
            if not roles:
                err("keine Rollen")
                continue
            for i, r in enumerate(roles, 1):
                print("   %3d> %s" % (i, r["label"]))
            sel = (await ainput("   Auswahl ('alle' = nur editierbare) ▸ "
                                )).strip()
            if sel.lower() in ("alle", "a", "*"):
                ids = [r["id"] for r in roles if r["editable"]]
                skip = len(roles) - len(ids)
                if skip:
                    note("%d nicht editierbare Rollen übersprungen" % skip)
            else:
                ids = [roles[i - 1]["id"]
                       for i in parse_selection(sel, len(roles))]
                ids = [i for i in ids
                       if next(r["editable"] for r in roles if r["id"] == i)]
            if not ids:
                err("keine editierbaren Rollen gewählt - abgebrochen")
                continue
            col = (await ainput("   Farbe (Hex, z.B. ff0000 oder #00aaff) ▸ "
                                )).strip()
            if not col:
                err("keine Farbe - abgebrochen")
                continue
            info("setze Farbe bei %d Rollen" % len(ids))
            await run_op(client, client.run_role_color(ids, col))
        else:
            note("unbekannte Wahl")
        print()


async def do_nuke(client):
    err("⚠ NUKE - Löschen ist unwiderruflich. Backups sind nur Doku.")
    opts = {}
    ren = (await ainput("   Kanäle umbenennen? [Name, Enter=nein] ▸ ")).strip()
    if ren:
        opts["rename"] = True
        opts["rename_to"] = ren
    srv = (await ainput("   Server-Name ändern? [Name, Enter=nein] ▸ ")).strip()
    if srv:
        opts["server_name"] = srv
    d = (await ainput("   ALLE Kanäle + Ordner LÖSCHEN? [ja/Enter=nein] ▸ "
                      )).strip().lower()
    if d in ("ja", "j", "yes"):
        w = (await ainput("   %sZum Bestätigen das Wort LÖSCHEN eingeben ▸ %s"
                          % (RED, R))).strip().upper()
        if w in ("LÖSCHEN", "LOESCHEN"):
            opts["delete"] = True
        else:
            note("nicht bestätigt - Löschen übersprungen")
    cre = (await ainput("   Neue Kanäle erstellen? [Anzahl, Enter=nein] ▸ "
                        )).strip()
    if cre.isdigit() and int(cre) > 0:
        opts["create_n"] = min(50, int(cre))
        cname = (await ainput("   Name dafür [secret!]: ")).strip()
        opts["create_name"] = cname or "secret!"
    note("Tipp: {invite} = dein Link, {n} = Nummer")
    post = (await ainput("   In Kanäle posten? Text eingeben [Enter=nein] ▸ "
                         )).strip()
    if post:
        opts["post"] = True
        opts["post_text"] = post
    if not opts:
        err("nichts gewählt - abgebrochen")
        return
    # Gate: exakter Servername
    want = client._status().get("guild", "")
    got = (await ainput("   %sSicherheit: tippe den Servernamen «%s» ▸ %s"
                        % (YELLOW, want, R))).strip()
    if got != want:
        err("Name stimmt nicht - abgebrochen")
        return
    info("NUKE gestartet: " + ", ".join(sorted(opts.keys())))
    await run_op(client, client.run_nuke(opts))


def print_members(lst):
    for i, m in enumerate(lst, 1):
        tag = (" [OWNER]" if m["owner"]
               else (" [BOT]" if m["bot"] else ""))
        nick = (" | %s" % m["nick"]) if m.get("nick") else ""
        top = (" | %s" % m["top"]) if m.get("top") else ""
        print("   %3d> %s%s%s%s" % (i, m["name"], nick, top, tag))


async def menu_members(client):
    info("lade Mitglieder ...")
    members, merr = await client._fetch_members()
    if merr:
        err(merr)
        if "Intent" in merr:
            note("Portal -> Applications -> SPECTRE -> Bot -> "
                 "Server Members Intent AN")
        return
    info("%d Mitglieder geladen" % len(members))
    aktuell = members
    while True:
        print("   [1] Liste anzeigen (%d)" % len(aktuell))
        print("   [2] Suchen (filtert die Liste, z.B. Namens-Anfang)")
        print("   [3] Nickname ändern - Auswahl")
        print("   [4] Nickname ändern - ALLE in der Liste")
        print("   [5] Kicken - Auswahl")
        print("   [6] ALLE in der Liste kicken")
        print("   [7] Filter zurücksetzen (alle %d)" % len(members))
        print("   [0] zurück")
        w = (await ainput("   %sMitglieder ▸ %s" % (YELLOW, R))).strip()
        if w == "0":
            return
        if w == "1":
            print_members(aktuell)
        elif w == "2":
            term = (await ainput("   Suchbegriff ▸ ")).strip().lower()
            if not term:
                continue
            aktuell = [m for m in aktuell
                       if term in (m["name"] or "").lower()
                       or term in (m.get("nick") or "").lower()]
            info("%d Treffer - alle Aktionen beziehen sich darauf" % len(aktuell))
            print_members(aktuell)
        elif w == "7":
            aktuell = members
            note("Filter zurückgesetzt (%d)" % len(aktuell))
        elif w in ("3", "4", "5", "6"):
            if not aktuell:
                err("Liste leer - [7] oder [2] nutzen")
                continue
            if w in ("3", "5"):
                print_members(aktuell)
                sel = (await ainput("   Auswahl ('alle' oder z.B. 1,3,5-8) ▸ "
                                    )).strip()
                if sel.lower() in ("alle", "a", "*"):
                    chosen = list(aktuell)
                else:
                    chosen = [aktuell[i - 1]
                              for i in parse_selection(sel, len(aktuell))]
                if not chosen:
                    err("keine Auswahl - abgebrochen")
                    continue
            else:
                chosen = list(aktuell)
            if w in ("3", "4"):
                if w == "4":
                    before = len(chosen)
                    chosen = [m for m in chosen
                              if str(m["id"]) != str(client.user.id)]
                    if len(chosen) != before:
                        note("eigener Bot-Eintrag übersprungen")
                pairs = [(m["id"], m["name"]) for m in chosen]
                if not pairs:
                    err("nichts zu ändern")
                    continue
                pat = (await ainput("   Nick-Muster ({n} = Nummer, "
                                    "{user} = Name) ▸ ")).strip()
                if not pat:
                    err("kein Muster - abgebrochen")
                    continue
                conf = (await ainput(
                    "   %s%d Nicknames -> %r setzen? [Enter=ja] ▸ %s"
                    % (YELLOW, len(pairs), pat, R))).strip().lower()
                if conf in ("n", "nein", "q", "x"):
                    note("abgebrochen")
                    continue
                info("setze %d Nicknames ..." % len(pairs))
                await run_op(client, client.run_setnick(pairs, pat))
            else:
                ids, skip = [], 0
                for m in chosen:
                    if m["bot"]:
                        skip += 1
                        continue
                    ids.append(m["id"])
                if skip:
                    note("%d Bot(s) übersprungen" % skip)
                if not ids:
                    err("nichts zum Kicken")
                    continue
                if w == "6":
                    conf = (await ainput(
                        "   %sALLE %d kicken? tippe KICK ▸ %s"
                        % (RED, len(ids), R))).strip().upper()
                    if conf != "KICK":
                        err("nicht bestätigt - abgebrochen")
                        continue
                else:
                    conf = (await ainput("   %d kicken? [ja/Enter=nein] ▸ "
                                         % len(ids))).strip().lower()
                    if conf not in ("ja", "j", "yes"):
                        note("abgebrochen")
                        continue
                reason = (await ainput("   Grund [SPECTRE Terminal]: ")).strip()
                info("kicke %d Mitglieder ..." % len(ids))
                await run_op(client, client.run_kick(
                    ids, reason or "SPECTRE Terminal"))
        else:
            note("unbekannte Wahl")
        print()


def show_status(client):
    d = client._status()
    if "error" in d:
        err(d["error"])
        return
    yn = lambda b: "OK  " if b else "FEHLT"
    c = d["can"]
    print(f"   {CYAN}Bot:{R} {d['user']}")
    print(f"   {CYAN}Server:{R} {d['guild']} (ID {d['gid']})")
    print(f"   {CYAN}Mitglieder:{R} {d['members']}")
    print(f"   {CYAN}Bot-Top-Rolle:{R} {d['top_role']} (pos {d['top_pos']})")
    print(f"   {CYAN}Rollen:{R} {len(d['roles'])} | "
          f"Kanäle/Ordner: {len(d['channels'])}")
    print()
    print("   Rechte:")
    print("     Server-Name aendern       : %s" % yn(c["server"]))
    print("     Kanaele (u/l/erstellen)   : %s" % yn(c["kanal"]))
    print("     Rollen umbenennen         : %s (nur pos < %d)"
          % (yn(c["rolle"]), d["top_pos"]))
    print("     Mitglieder kicken         : %s" % yn(c["kick"]))
    print("     Nicknames anderer aendern : %s" % yn(c["nick"]))
    print("     Einladung erstellen       : %s" % yn(c["invite"]))
    print("     Nachrichten senden        : %s" % yn(c["send"]))
    print()
    note("Backups: " + BACKUP_DIR)
    note("Members-Intent: siehe [10] (403 = im Portal fehlt)")


# ---------------------------------------------------------------- Menue
async def menu(client):
    show_banner()
    while True:
        data = client._status()
        if "error" in data:
            err(data["error"])
            return
        c = data["can"]
        fl = ("Server%s Kanaele%s Rollen%s Kick%s Nick%s Senden%s"
              % tuple(("✔" if c[k] else "✘") for k in
                      ("server", "kanal", "rolle", "kick", "nick", "send")))
        print(f"{GRAY}-" * 62 + R)
        print(f"   {WHITE}{BOLD}Server:{R} {data['guild']}  "
              f"{WHITE}{BOLD}Bot:{R} {data['user']}  "
              f"{WHITE}{BOLD}Member:{R} {data['members']}")
        print(f"   {GRAY}Rechte: {fl} | Strg+C = Stop{R}")
        print(f"{GRAY}-" * 62 + R)
        print(f"   [1]  Ziele anzeigen (Kanäle + Threads)")
        print(f"   [2]  SPAM - Text")
        print(f"   [3]  SPAM - Text + Links")
        print(f"   [4]  SPAM - BILDER")
        print(f"   [5]  SPAM - Mix (Text + Links + Bilder)")
        print(f"   [6]  Server (Name / Icon / Beschreibung)")
        print(f"   [7]  Kanäle (umbenennen / Slowmode)")
        print(f"   [8]  Rollen (umbenennen / Farbe)")
        print(f"   [9]  NUKE (umbenennen/löschen/erstellen/posten)")
        print(f"   [10] Mitglieder (Liste/Suche/Nick/Kick)")
        print(f"   [11] Status / Rechte")
        print(f"   [0]  Beenden")
        try:
            choice = (await ainput(f"   {YELLOW}Wahl ▸ {R}")).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n   {GRAY}Abbruch.{R}\n")
            return
        try:
            if choice == "0":
                print(f"\n   {GRAY}Bis dann. {R}\n")
                return
            elif choice == "1":
                await do_targets_view(client)
            elif choice == "2":
                await do_spam(client, "text")
            elif choice == "3":
                await do_spam(client, "link")
            elif choice == "4":
                await do_spam(client, "bild")
            elif choice == "5":
                await do_spam(client, "mix")
            elif choice == "6":
                await menu_server(client)
            elif choice == "7":
                await menu_channels(client)
            elif choice == "8":
                await menu_roles(client)
            elif choice == "9":
                await do_nuke(client)
            elif choice == "10":
                await menu_members(client)
            elif choice == "11":
                show_status(client)
            elif choice:
                err("unbekannte Wahl: " + choice)
        except EOFError:
            print(f"\n   {GRAY}Eingabe beendet.{R}\n")
            return
        except KeyboardInterrupt:
            client.stop_flag = True
            print(f"\n   {YELLOW}Unterbrochen - Lauf gestoppt.{R}")
        print()


# ---------------------------------------------------------------- Start
def main():
    token = load_token()
    events = queue.Queue()
    selftest = "--selftest" in sys.argv
    test_spam = "--test-spam" in sys.argv
    client = TermClient(events, selftest=selftest or test_spam,
                        test_spam=test_spam)

    if selftest or test_spam:
        try:
            asyncio.run(client.start(token))
        except discord.LoginFailure:
            print("LOGIN_BAD")
            return 2
        except KeyboardInterrupt:
            print("\nABBRUCH")
            return 130
        except Exception as e:
            print("FEHLER", type(e).__name__, str(e)[:160])
            return 1
        return 0

    async def amain():
        task = asyncio.ensure_future(client.start(token))
        ready = False
        for _ in range(600):
            if client.loop_ref is not None:
                ready = True
                break
            await asyncio.sleep(0.1)
        if not ready:
            err("keine Gateway-Verbindung (30s) - Token prüfen?")
            return
        try:
            await menu(client)
        finally:
            client.stop_flag = True
            try:
                await client.close()
            except Exception:
                pass
            try:
                await asyncio.wait_for(task, 5)
            except Exception:
                pass

    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        print(f"\n   {YELLOW}Strg+C - gestoppt.{R} | gesendet: "
              f"{client.stats['sent']}, Fehler: {client.stats['err']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
