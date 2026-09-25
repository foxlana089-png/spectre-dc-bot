# -*- coding: utf-8 -*-
"""SPECTRE Server-Panel

Alles-aendern-Werkzeug fuer den eigenen Server (nur der Bot-Server):
- Umbenennen: Server-Name, Kanaele, Rollen (Backup vor jedem Massenlauf)
- NUKE: loeschen/erstellen/posten (mit Links) - Doppel-Sicherheit
- Mitglieder: laden, Nicknames (nur Terminal), kicken (braucht Recht
  "Mitglieder kicken" + Members-Intent; Owner ist von Discord gesperrt)
- Status: Rechte-Checkliste, was fehlt und wo

Grenzen: nur eigener Server, kein Ban, kein Loeschen von Mitgliederdaten,
Kick/Nuke nur nach Haeckchen-Bestaetigung. Deckel: kicked wird nur,
was in der Liste geladen ist.

Start: Doppelklick Desktop-Verknuepfung "SPECTRE Server-Panel".
"""
import asyncio
import json
import logging
import os
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import messagebox, ttk

import aiohttp
import discord

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "bot_config.json")
BACKUP_DIR = os.path.join(HERE, "backups")
API = "https://discord.com/api/v10"

logging.basicConfig(level=logging.WARNING, handlers=[logging.NullHandler()])
logging.getLogger("discord").setLevel(logging.WARNING)

SENDABLE = (discord.ChannelType.text, discord.ChannelType.news,
            discord.ChannelType.voice)
POSTABLE = (discord.ChannelType.text, discord.ChannelType.news)


def load_token():
    with open(CFG, encoding="utf-8") as f:
        return json.load(f)["token"]


def ts():
    return time.strftime("%Y%m%d_%H%M%S")


def save_backup(kind, lines):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, "panel_%s_%s.txt" % (kind, ts()))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


class PanelClient(discord.Client):
    def __init__(self, events, selftest=False):
        super().__init__(intents=discord.Intents.default())
        self.events = events
        self.selftest = selftest
        self.stop_flag = False
        self._once = False
        self.loop_ref = None
        self.my_session = None

    async def close(self):
        if self.my_session is not None and not self.my_session.closed:
            await self.my_session.close()
            self.my_session = None
        await super().close()

    def emit(self, *item):
        self.events.put(item)

    # ---------------- Ready / Status ----------------
    async def on_ready(self):
        if self._once:
            return
        self._once = True
        try:
            self.loop_ref = asyncio.get_running_loop()
            if self.my_session is None:
                self.my_session = aiohttp.ClientSession(headers={
                    "Authorization": self._auth(),
                    "User-Agent": "SPECTRE-Panel/1.0"})
            data = self._status()
            self.emit("ready", data)
            if self.selftest:
                await self._selftest(data)
        except Exception:
            traceback.print_exc()
            print("ON_READY_FEHLER", flush=True)
            if self.selftest:
                await self.close()

    async def refresh(self):
        try:
            self.emit("ready", self._status())
        except Exception as e:
            self.emit("log", "Refresh fehlgeschlagen: %s" % str(e)[:100])

    def _status(self):
        g = self.guilds[0] if self.guilds else None
        if g is None:
            return {"error": "kein Server (Bot ist in keiner Guild)"}
        me = g.me
        p = me.guild_permissions
        top = max(me.roles, key=lambda r: r.position)
        channels, roles = [], []
        for ch in g.channels:
            if isinstance(ch, discord.CategoryChannel):
                channels.append({"id": ch.id, "kind": "ordner", "sendable": False,
                                 "label": "[Ordner] %s" % ch.name})
                continue
            t = ch.type
            if t in SENDABLE:
                mark = "\U0001f4ac" if t == discord.ChannelType.text else (
                    "\U0001f4e2" if t == discord.ChannelType.news else "\U0001f50a")
            elif t == discord.ChannelType.forum:
                mark = "\U0001f4cb"
            else:
                mark = "\U0001f3ae"
            par = " (%s)" % ch.category.name if ch.category else ""
            channels.append({"id": ch.id, "kind": "kanal",
                             "sendable": t in POSTABLE,
                             "label": "%s #%s%s" % (mark, ch.name, par)})
        for r in g.roles:
            editable = (not r.managed) and r.position < top.position
            label = "%s (pos %d)%s%s" % (
                r.name, r.position,
                " [managed]" if r.managed else "",
                "" if editable else " [nicht editierbar]")
            roles.append({"id": r.id, "label": label, "editable": editable,
                          "managed": r.managed})
        return {
            "user": str(self.user),
            "guild": g.name, "gid": g.id,
            "members": g.member_count,
            "top_role": top.name, "top_pos": top.position,
            "can": {
                "server": bool(p.manage_guild),
                "kanal": bool(p.manage_channels),
                "rolle": bool(p.manage_roles),
                "kick": bool(p.kick_members),
                "invite": bool(p.create_instant_invite),
                "send": bool(p.send_messages),
                "nick": bool(p.manage_nicknames),
            },
            "channels": channels, "roles": roles,
        }

    async def _selftest(self, data):
        if "error" in data:
            print("SELFTEST_FEHLER:", data["error"])
            await self.close()
            return
        print("ANGEMELDET:", data["user"])
        print("SERVER:", data["guild"], "| MEMBER:", data["members"])
        print("TOP-ROLLE:", data["top_role"], "pos", data["top_pos"],
              "| ROLLEN:", len(data["roles"]), "| KANAELE/ORDNER:", len(data["channels"]))
        for k, v in data["can"].items():
            print("  RECHT %-7s: %s" % (k, "OK" if v else "FEHLT"))
        members, err = await self._fetch_members(limit=3)
        print("MEMBER-SONDE:", "OK (erste %d)" % len(members) if err is None
              else "FEHLT: " + err)
        g = self.guilds[0]
        # seitenwirkungsfreie Sonden: PATCH mit identischem Wert (kein
        # sichtbarer Nick-Aender) + DELETE auf id "1" (existiert nicht)
        try:
            st1, _ = await self._session_patch(
                "%s/guilds/%d/members/@me" % (API, g.id),
                {"nick": g.me.nick})
            print("PATCH-SONDE:", st1,
                  "(200 = Auth/PATCH OK, eigener Nick unveraendert)")
        except Exception as e:
            print("PATCH-SONDE: FEHLER", str(e)[:90])
        try:
            st2, _ = await self._session_delete(
                "%s/guilds/%d/members/1" % (API, g.id))
            print("DELETE-SONDE:", st2, "(404 erwartet = Auth/Endpunkt OK, "
                                         "401/403 = Problem)")
        except Exception as e:
            print("DELETE-SONDE: FEHLER", str(e)[:90])
        print("SELFTEST_OK")
        await self.close()

    # ---------------- Roh-REST (eigene Rate-Limit-Behandlung) ----------------
    def _auth(self):
        a = self.http.token
        return a if a.lower().startswith("bot ") else "Bot " + a

    async def _session_get(self, url, params=None):
        for _ in range(5):
            async with self.my_session.get(url, params=params) as r:
                if r.status == 429:
                    try:
                        d = await r.json()
                    except Exception:
                        d = {}
                    await asyncio.sleep(float(d.get("retry_after", 1)) or 1)
                    continue
                return r.status, await r.text()
        return 429, "Rate-Limit"

    async def _session_delete(self, url, reason=None):
        headers = {}
        if reason:
            headers["X-Audit-Log-Reason"] = reason[:500]
        for _ in range(5):
            async with self.my_session.delete(url, headers=headers) as r:
                if r.status == 429:
                    try:
                        d = await r.json()
                    except Exception:
                        d = {}
                    await asyncio.sleep(float(d.get("retry_after", 1)) or 1)
                    continue
                if r.status >= 400:
                    return r.status, await r.text()
                return r.status, ""
        return 429, "Rate-Limit"

    async def _session_patch(self, url, payload, reason=None):
        headers = {"Content-Type": "application/json"}
        if reason:
            headers["X-Audit-Log-Reason"] = reason[:500]
        body = json.dumps(payload).encode("utf-8")
        for _ in range(5):
            async with self.my_session.patch(url, data=body,
                                             headers=headers) as r:
                if r.status == 429:
                    try:
                        d = await r.json()
                    except Exception:
                        d = {}
                    await asyncio.sleep(float(d.get("retry_after", 1)) or 1)
                    continue
                return r.status, await r.text()
        return 429, "Rate-Limit"

    # ---------------- Mitglieder ----------------
    async def _fetch_members(self, limit=0):
        """Liest Mitglieder roh aus. limit=0 -> alle. Rueckgabe: (liste, fehler|None)."""
        g = self.guilds[0]
        out, after = [], "0"
        while True:
            params = {"limit": 1000, "after": after}
            status, body = await self._session_get(
                "%s/guilds/%d/members" % (API, g.id), params=params)
            if status in (401, 403):
                return out, "HTTP%d - Server-Members-Intent fehlt (Portal -> Bot -> Intents)" % status
            if status != 200:
                return out, "HTTP%d %s" % (status, body[:80])
            try:
                batch = json.loads(body)
            except Exception:
                return out, "Antwort kaputt"
            if not batch:
                break
            role_pos = {r.id: r.position for r in g.roles}
            role_name = {r.id: r.name for r in g.roles}
            for m in batch:
                u = m.get("user") or {}
                top_id, best = None, -1
                for rid in (m.get("roles") or []):
                    try:
                        p = role_pos.get(int(rid), -1)
                    except (TypeError, ValueError):
                        continue
                    if p > best:
                        best, top_id = p, int(rid)
                out.append({
                    "id": u.get("id"),
                    "name": u.get("global_name") or u.get("username") or "?",
                    "nick": m.get("nick"),
                    "top": role_name.get(top_id) or g.default_role.name,
                    "bot": bool(u.get("bot")),
                    "owner": str(u.get("id")) == str(g.owner_id),
                })
            if limit and len(out) >= limit:
                out = out[:limit]
                break
            if len(batch) < 1000:
                break
            after = batch[-1]["user"]["id"]
        return out, None

    async def load_members(self):
        self.emit("log", "lade Mitglieder ...")
        members, err = await self._fetch_members()
        self.emit("members", members, err)

    async def run_kick(self, ids, reason):
        g = self.guilds[0]
        self.stop_flag = False
        sent = err = 0
        total = len(ids)
        self.emit("prog", 0, total, "kicke ...")
        for mid in ids:
            if self.stop_flag:
                break
            if str(mid) == str(g.owner_id):
                err += 1
                self.emit("log", "OWNER (id %s): Discord erlaubt grundsätzlich "
                                 "KEINEN Kick/Ban des Owners - das kann nur der "
                                 "Owner selbst durch Verlassen oder "
                                 "Ownerschaftsübertragung" % mid)
                continue
            status, body = await self._session_delete(
                "%s/guilds/%d/members/%s" % (API, g.id, mid), reason=reason)
            if status in (200, 204):
                sent += 1
                self.emit("prog", sent, total, "gekickt")
            else:
                err += 1
                if status == 403:
                    self.emit("log", "KEIN-RECHT(403) beim Kicken "
                                     "(Rollen-Hierarchie oder Recht fehlt)")
                else:
                    self.emit("log", "Kick HTTP%d %s" % (status, body[:70]))
            await asyncio.sleep(0.05)
        self.emit("done", "kick", sent, err)

    # ---------------- Umbenennen ----------------
    async def set_server_name(self, name):
        g = self.guilds[0]
        old = g.name
        path = save_backup("server_vor_rename", ["alt: " + old, "neu: " + name])
        try:
            await g.edit(name=name)
            self.emit("log", "Server-Name: %r -> %r (Backup: %s)"
                      % (old, name, os.path.basename(path)))
            self.emit("done", "server", 1, 0)
        except Exception as e:
            self.emit("log", "Server-Name Fehler: %s" % str(e)[:120])
            self.emit("done", "server", 0, 1)

    async def run_rename_channels(self, ids, name):
        self.stop_flag = False
        g = self.guilds[0]
        before = []
        for cid in ids:
            ch = self.get_channel(cid)
            before.append("%d|%s" % (cid, ch.name if ch else "?"))
        path = save_backup("kanal_vor_rename", before)
        self.emit("log", "Backup: %s" % os.path.basename(path))
        sent = err = 0
        total = len(ids)
        self.emit("prog", 0, total, "benenne Kanäle um ...")
        for cid in ids:
            if self.stop_flag:
                break
            try:
                ch = self.get_channel(cid) or await self.fetch_channel(cid)
                await ch.edit(name=name)
                sent += 1
                self.emit("prog", sent, total, ch.name)
            except discord.Forbidden:
                err += 1
                self.emit("log", "KEIN-RECHT(403): Kanal %s" % cid)
            except Exception as e:
                err += 1
                self.emit("log", "Kanal-Fehler: %s" % str(e)[:100])
        self.emit("done", "kanal", sent, err)

    async def run_rename_roles(self, ids, name):
        self.stop_flag = False
        g = self.guilds[0]
        before = []
        for rid in ids:
            r = g.get_role(rid)
            if r:
                before.append("%d|%s|#%06x" % (rid, r.name, r.color.value))
        path = save_backup("rolle_vor_rename", before)
        self.emit("log", "Backup: %s" % os.path.basename(path))
        sent = err = 0
        total = len(ids)
        self.emit("prog", 0, total, "benenne Rollen um ...")
        for rid in ids:
            if self.stop_flag:
                break
            r = g.get_role(rid)
            if r is None:
                err += 1
                continue
            if r.managed:
                err += 1
                self.emit("log", "übersprungen (managed): %s" % r.name)
                continue
            try:
                await r.edit(name=name)
                sent += 1
                self.emit("prog", sent, total, r.name)
            except discord.Forbidden:
                err += 1
                self.emit("log", "KEIN-RECHT(403): Rolle %s" % r.name)
            except Exception as e:
                err += 1
                self.emit("log", "Rollen-Fehler: %s" % str(e)[:100])
        self.emit("done", "rolle", sent, err)

    # ---------------- Nuke ----------------
    async def _invite_link(self, g):
        try:
            if getattr(g, "vanity_url_code", None):
                return "https://discord.gg/" + g.vanity_url_code
        except Exception:
            pass
        try:
            invs = await g.invites()
            if invs:
                return "https://discord.gg/" + invs[0].code
        except Exception:
            pass
        return None

    async def run_nuke(self, opts):
        g = self.guilds[0]
        self.stop_flag = False
        srv = (opts.get("server_name") or "").strip()
        do_delete = bool(opts.get("delete"))
        create_n = int(opts.get("create_n") or 0)
        create_name = (opts.get("create_name") or "secret!").strip() or "secret!"
        ren_to = (opts.get("rename_to") or "").strip()
        do_rename = bool(opts.get("rename")) and ren_to
        post = bool(opts.get("post"))
        post_text = (opts.get("post_text") or "").strip()

        cats = [c for c in g.channels if isinstance(c, discord.CategoryChannel)]
        plain = [c for c in g.channels if not isinstance(c, discord.CategoryChannel)]
        if do_delete:
            path = save_backup("nuke_vor_delete", [
                "%d|%s|%s" % (c.id, c.type, c.name) for c in g.channels])
            self.emit("log", "Backup (nicht rueckgaengig, nur Dokumentation): %s"
                      % os.path.basename(path))

        planned = 0
        if srv:
            planned += 1
        if do_delete:
            planned += len(plain) + len(cats)
        planned += create_n if create_n > 0 else 0
        if do_rename and not do_delete:
            planned += len(plain)
        if post:
            planned += 1  # Gesamtzaehler, echte Treffer im Log
        planned = max(planned, 1)
        sent = err = 0
        self.emit("prog", 0, planned, "nuke startet ...")

        def step(label):
            nonlocal sent
            sent += 1
            self.emit("prog", sent, planned, label)

        # 1) Server-Name
        if srv and not self.stop_flag:
            try:
                await g.edit(name=srv)
                step("Server-Name -> %s" % srv)
                self.emit("log", "Server-Name geändert: %r" % srv)
            except Exception as e:
                err += 1
                self.emit("log", "Server-Name Fehler: %s" % str(e)[:100])

        # 2) Loeschen (Kanaele zuerst, dann Ordner)
        if do_delete:
            for ch in plain:
                if self.stop_flag:
                    break
                try:
                    await ch.delete(reason="SPECTRE nuke (User-Aktion)")
                    step("gelöscht: %s" % ch.name)
                except discord.Forbidden:
                    err += 1
                    self.emit("log", "KEIN-RECHT(403): %s" % ch.name)
                except Exception as e:
                    err += 1
                    self.emit("log", "Löschen-Fehler %s: %s"
                              % (ch.name, str(e)[:80]))
            for c in cats:
                if self.stop_flag:
                    break
                try:
                    await c.delete(reason="SPECTRE nuke (User-Aktion)")
                    step("gelöscht (Ordner): %s" % c.name)
                except Exception as e:
                    err += 1
                    self.emit("log", "Ordner-Fehler %s: %s"
                              % (c.name, str(e)[:80]))

        # 3) Neue Kanaele
        created = []
        if create_n > 0 and not self.stop_flag:
            for i in range(create_n):
                try:
                    ch = await g.create_text_channel(name=create_name)
                    created.append(ch)
                    step("erstellt: #%s" % ch.name)
                except Exception as e:
                    err += 1
                    self.emit("log", "Erstellen-Fehler: %s" % str(e)[:80])

        # 4) Umbenennen (nur wenn nicht geloescht)
        if do_rename and not do_delete and not self.stop_flag:
            for ch in plain:
                if self.stop_flag:
                    break
                try:
                    await ch.edit(name=ren_to)
                    step("umbenannt: %s" % ch.name)
                except discord.Forbidden:
                    err += 1
                    self.emit("log", "KEIN-RECHT(403): %s" % ch.name)
                except Exception as e:
                    err += 1
                    self.emit("log", "Umbenennen-Fehler: %s" % str(e)[:80])

        # 5) Posten (mit {invite})
        if post and post_text and not self.stop_flag:
            link = None
            if "{invite}" in post_text:
                link = await self._invite_link(g)
                if link is None:
                    self.emit("log", "kein Einladungs-Link gefunden "
                                     "(Recht 'Einladung erstellen' fehlt?) - "
                                     "Text ohne Link gepostet")
            text = post_text.replace("{invite}", link or "(kein Link verfügbar)")
            if created:
                targets = created
            else:
                targets = [c for c in g.channels if c.type in POSTABLE]
            ok = fail = 0
            for i, ch in enumerate(targets, 1):
                if self.stop_flag:
                    break
                try:
                    await ch.send(text.replace("{n}", str(i)))
                    ok += 1
                    self.emit("prog", sent, planned, "poste: %s" % ch.name)
                except discord.Forbidden:
                    fail += 1
                except Exception as e:
                    fail += 1
                    self.emit("log", "Post-Fehler %s: %s"
                              % (ch.name, str(e)[:80]))
            step("posten: %d ok, %d Fehler" % (ok, fail))
            self.emit("log", "gepostet in %d Kanälen (%d Fehler)"
                      % (ok, fail))

        self.emit("done", "nuke", sent, err)


class App:
    def __init__(self, root, events, client):
        self.root = root
        self.q = events
        self.client = client
        self.data = None
        self.shown_ch = []
        self.shown_ro = []
        self.members = []
        self.running = False

        bg, fg, dim = "#0f0f12", "#e8e8ea", "#9a9aa2"
        font = ("Segoe UI", 9)
        fontb = ("Segoe UI", 10, "bold")
        self.fg = fg

        root.title("SPECTRE Server-Panel")
        root.configure(bg=bg)
        root.geometry("700x800")
        root.minsize(640, 700)

        tk.Label(root, text="SPECTRE SERVER-PANEL", font=("Segoe UI", 13, "bold"),
                 bg=bg, fg="#ffffff").pack(pady=(8, 0))
        self.status_lbl = tk.Label(root, text="verbinde ...", font=font,
                                   bg=bg, fg=dim)
        self.status_lbl.pack()

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(8, 0))

        # ---------- Tab 1: Umbenennen ----------
        t1 = tk.Frame(self.nb, bg=bg)
        self.nb.add(t1, text=" Umbenennen ")

        r0 = tk.Frame(t1, bg=bg)
        r0.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(r0, text="Server-Name:", font=font, bg=bg, fg=fg).pack(side="left")
        self.srv_entry = tk.Entry(r0, font=font, bg="#17171b", fg=fg,
                                  insertbackground=fg, width=28)
        self.srv_entry.pack(side="left", padx=6)
        tk.Button(r0, text="Anwenden", command=self.do_server_name, font=font,
                  bg="#26262c", fg=fg, activebackground="#33333a",
                  relief="flat", padx=8).pack(side="left")

        # Kanaele
        cf = tk.LabelFrame(t1, text=" Kanäle ", font=font, bg=bg, fg=fg)
        cf.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        b1 = tk.Frame(cf, bg=bg)
        b1.pack(fill="x", padx=6, pady=(4, 0))
        for txt, cmd in (("Alle", self.ch_all), ("Keine", self.ch_none),
                         ("Nur Textkanäle", self.ch_text)):
            tk.Button(b1, text=txt, command=cmd, font=font, bg="#26262c", fg=fg,
                      activebackground="#33333a", relief="flat",
                      padx=6).pack(side="left", padx=(0, 5))
        self.ch_lb = tk.Listbox(cf, selectmode="extended", height=8, bg="#17171b",
                                fg=fg, selectbackground="#3d3d45",
                                selectforeground="#ffffff", bd=0, font=font)
        self.ch_lb.pack(fill="both", expand=True, padx=6, pady=4)
        r1 = tk.Frame(cf, bg=bg)
        r1.pack(fill="x", padx=6, pady=(0, 6))
        tk.Label(r1, text="Neuer Name:", font=font, bg=bg, fg=fg).pack(side="left")
        self.ch_name = tk.Entry(r1, font=font, bg="#17171b", fg=fg,
                                insertbackground=fg, width=22)
        self.ch_name.pack(side="left", padx=6)
        tk.Button(r1, text="Auswahl umbenennen", command=self.do_rename_channels,
                  font=font, bg="#1f6feb", fg="#ffffff", activebackground="#2a7ffb",
                  relief="flat", padx=8).pack(side="left")

        # Rollen
        rf = tk.LabelFrame(t1, text=" Rollen ", font=font, bg=bg, fg=fg)
        rf.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        b2 = tk.Frame(rf, bg=bg)
        b2.pack(fill="x", padx=6, pady=(4, 0))
        for txt, cmd in (("Alle", self.ro_all), ("Keine", self.ro_none)):
            tk.Button(b2, text=txt, command=cmd, font=font, bg="#26262c", fg=fg,
                      activebackground="#33333a", relief="flat",
                      padx=6).pack(side="left", padx=(0, 5))
        tk.Label(b2, text="[nicht editierbar] = Position zu hoch / managed",
                 font=("Segoe UI", 8), bg=bg, fg=dim).pack(side="right")
        self.ro_lb = tk.Listbox(rf, selectmode="extended", height=7, bg="#17171b",
                                fg=fg, selectbackground="#3d3d45",
                                selectforeground="#ffffff", bd=0, font=font)
        self.ro_lb.pack(fill="both", expand=True, padx=6, pady=4)
        r2 = tk.Frame(rf, bg=bg)
        r2.pack(fill="x", padx=6, pady=(0, 6))
        tk.Label(r2, text="Neuer Name:", font=font, bg=bg, fg=fg).pack(side="left")
        self.ro_name = tk.Entry(r2, font=font, bg="#17171b", fg=fg,
                                insertbackground=fg, width=22)
        self.ro_name.pack(side="left", padx=6)
        tk.Button(r2, text="Auswahl umbenennen", command=self.do_rename_roles,
                  font=font, bg="#1f6feb", fg="#ffffff", activebackground="#2a7ffb",
                  relief="flat", padx=8).pack(side="left", padx=(0, 6))
        tk.Button(r2, text="Alle umbenennen", command=self.do_rename_roles_all,
                  font=font, bg="#1f6feb", fg="#ffffff", activebackground="#2a7ffb",
                  relief="flat", padx=8).pack(side="left")

        # ---------- Tab 2: Nuke ----------
        t2 = tk.Frame(self.nb, bg=bg)
        self.nb.add(t2, text=" NUKE ⚠ ")
        tk.Label(t2, text="⚠ Alles hier ist unwiderruflich - Backups sind nur "
                          "Dokumentation!",
                 font=("Segoe UI", 9, "bold"), bg=bg, fg="#ff6b6b").pack(
            fill="x", padx=10, pady=(8, 0))

        self.opt_srv = tk.IntVar(value=0)
        self.opt_del = tk.IntVar(value=0)
        self.opt_cre = tk.IntVar(value=0)
        self.opt_post = tk.IntVar(value=0)
        self.gate_ok = tk.IntVar(value=0)

        of = tk.Frame(t2, bg=bg)
        of.pack(fill="x", padx=12, pady=6)

        rr = tk.Frame(of, bg=bg)
        rr.pack(fill="x", pady=2)
        tk.Checkbutton(rr, text="Server-Name ändern ->", variable=self.opt_srv,
                       command=self._gate, bg=bg, fg=fg, selectcolor="#17171b",
                       activebackground=bg, activeforeground=fg).pack(side="left")
        self.nuke_srv = tk.Entry(rr, font=font, bg="#17171b", fg=fg,
                                 insertbackground=fg, width=24)
        self.nuke_srv.pack(side="left", padx=6)
        self.nuke_srv.insert(0, "secret!")

        rr = tk.Frame(of, bg=bg)
        rr.pack(fill="x", pady=2)
        tk.Checkbutton(rr, text="ALLE Kanäle + Ordner löschen (unwiderruflich!)",
                       variable=self.opt_del, command=self._gate, bg=bg, fg=fg,
                       selectcolor="#17171b", activebackground=bg,
                       activeforeground=fg).pack(side="left")

        rr = tk.Frame(of, bg=bg)
        rr.pack(fill="x", pady=2)
        tk.Checkbutton(rr, text="Neue Kanäle erstellen:", variable=self.opt_cre,
                       command=self._gate, bg=bg, fg=fg, selectcolor="#17171b",
                       activebackground=bg, activeforeground=fg).pack(side="left")
        self.nuke_cre_n = tk.Spinbox(rr, from_=1, to=50, width=4, font=font,
                                     textvariable=tk.StringVar(value="3"))
        self.nuke_cre_n.pack(side="left", padx=4)
        tk.Label(rr, text="x Name:", font=font, bg=bg, fg=fg).pack(side="left")
        self.nuke_cre_name = tk.Entry(rr, font=font, bg="#17171b", fg=fg,
                                      insertbackground=fg, width=18)
        self.nuke_cre_name.pack(side="left", padx=4)
        self.nuke_cre_name.insert(0, "secret!")

        rr = tk.Frame(of, bg=bg)
        rr.pack(fill="x", pady=2)
        tk.Checkbutton(rr, text="Nachricht in Kanäle posten ({invite} = Link, "
                                "{n} = Nummer):",
                       variable=self.opt_post, command=self._gate, bg=bg, fg=fg,
                       selectcolor="#17171b", activebackground=bg,
                       activeforeground=fg).pack(anchor="w")
        self.nuke_post = tk.Text(rr, height=3, bg="#17171b", fg=fg,
                                 insertbackground=fg, bd=0, font=font, width=60)
        self.nuke_post.pack(fill="x", pady=(2, 0))
        self.nuke_post.insert("1.0", "Achtung! Server-Neustart - komm zurück: "
                                     "{invite}")

        gf = tk.LabelFrame(t2, text=" Sicherheit ", font=font, bg=bg, fg=fg)
        gf.pack(fill="x", padx=12, pady=(10, 0))
        gr = tk.Frame(gf, bg=bg)
        gr.pack(fill="x", padx=8, pady=6)
        tk.Label(gr, text="Tippe zum Freischalten den aktuellen Servernamen:",
                 font=font, bg=bg, fg=fg).pack(anchor="w")
        gr2 = tk.Frame(gf, bg=bg)
        gr2.pack(fill="x", padx=8, pady=(2, 8))
        self.gate_entry = tk.Entry(gr2, font=font, bg="#17171b", fg=fg,
                                   insertbackground=fg, width=24)
        self.gate_entry.pack(side="left", padx=(0, 10))
        self.gate_entry.bind("<KeyRelease>", lambda e: self._gate())
        tk.Checkbutton(gr2, text="Mir ist klar - unwiderruflich",
                       variable=self.gate_ok, command=self._gate, bg=bg, fg=fg,
                       selectcolor="#17171b", activebackground=bg,
                       activeforeground=fg).pack(side="left")

        br = tk.Frame(t2, bg=bg)
        br.pack(fill="x", padx=12, pady=8)
        tk.Button(br, text="Vorschau", command=self.nuke_preview, font=font,
                  bg="#26262c", fg=fg, activebackground="#33333a",
                  relief="flat", padx=10).pack(side="left")
        self.nuke_btn = tk.Button(br, text="▶  NUCKE STARTEN",
                                  command=self.do_nuke, font=fontb, bg="#b02a30",
                                  fg="#ffffff", activebackground="#c93a40",
                                  relief="flat", padx=16, pady=4,
                                  state="disabled")
        self.nuke_btn.pack(side="left", padx=10)

        # ---------- Tab 3: Mitglieder ----------
        t3 = tk.Frame(self.nb, bg=bg)
        self.nb.add(t3, text=" Mitglieder ")
        mr = tk.Frame(t3, bg=bg)
        mr.pack(fill="x", padx=10, pady=(8, 0))
        tk.Button(mr, text="Mitglieder laden", command=self.do_load_members,
                  font=font, bg="#26262c", fg=fg, activebackground="#33333a",
                  relief="flat", padx=8).pack(side="left")
        self.mem_lbl = tk.Label(mr, text="noch nicht geladen", font=font,
                                bg=bg, fg=dim)
        self.mem_lbl.pack(side="left", padx=8)

        self.mem_lb = tk.Listbox(t3, selectmode="extended", bg="#17171b", fg=fg,
                                 selectbackground="#3d3d45",
                                 selectforeground="#ffffff", bd=0, font=font)
        self.mem_lb.pack(fill="both", expand=True, padx=10, pady=6)

        rr = tk.Frame(t3, bg=bg)
        rr.pack(fill="x", padx=10)
        tk.Label(rr, text="Grund:", font=font, bg=bg, fg=fg).pack(side="left")
        self.kick_reason = tk.Entry(rr, font=font, bg="#17171b", fg=fg,
                                    insertbackground=fg, width=30)
        self.kick_reason.pack(side="left", padx=6)
        self.kick_reason.insert(0, "SPECTRE Server-Panel")

        self.kick_ok = tk.IntVar(value=0)
        tk.Checkbutton(t3, text="Mir ist klar - KICK ist nicht rückgängig zu "
                                "machen (nur über Einladung zurück)",
                       variable=self.kick_ok, command=self._gate, bg=bg, fg=fg,
                       selectcolor="#17171b", activebackground=bg,
                       activeforeground=fg).pack(anchor="w", padx=10, pady=(6, 0))

        br = tk.Frame(t3, bg=bg)
        br.pack(fill="x", padx=10, pady=(4, 8))
        self.kick_sel_btn = tk.Button(br, text="Auswahl kicken",
                                      command=self.do_kick_sel, font=fontb,
                                      bg="#b02a30", fg="#ffffff",
                                      activebackground="#c93a40",
                                      relief="flat", padx=12, pady=4,
                                      state="disabled")
        self.kick_sel_btn.pack(side="left", padx=(0, 8))
        self.kick_all_btn = tk.Button(br, text="ALLE kicken (geladene)",
                                      command=self.do_kick_all, font=fontb,
                                      bg="#b02a30", fg="#ffffff",
                                      activebackground="#c93a40",
                                      relief="flat", padx=12, pady=4,
                                      state="disabled")
        self.kick_all_btn.pack(side="left")

        # ---------- Tab 4: Status ----------
        t4 = tk.Frame(self.nb, bg=bg)
        self.nb.add(t4, text=" Status ")
        tk.Button(t4, text="Aktualisieren", command=self.do_refresh, font=font,
                  bg="#26262c", fg=fg, activebackground="#33333a",
                  relief="flat", padx=8).pack(anchor="w", padx=10, pady=(8, 0))
        self.st_txt = tk.Text(t4, bg="#17171b", fg=fg, bd=0,
                              font=("Consolas", 9))
        self.st_txt.pack(fill="both", expand=True, padx=10, pady=6)
        self.st_txt.configure(state="disabled")

        # ---------- unten: Fortschritt + Log ----------
        pr = tk.Frame(root, bg=bg)
        pr.pack(fill="x", padx=10, pady=(6, 0))
        self.stop_btn = tk.Button(pr, text="■  STOP", command=self.do_stop,
                                  font=fontb, bg="#b02a30", fg="#ffffff",
                                  activebackground="#c93a40", relief="flat",
                                  padx=14, pady=3)
        self.stop_btn.pack(side="left")
        self.bar = ttk.Progressbar(pr, maximum=1, mode="determinate")
        self.bar.pack(side="left", fill="x", expand=True, padx=8)
        self.prog_lbl = tk.Label(pr, text="0/0", font=font, bg=bg, fg=fg)
        self.prog_lbl.pack(side="right")

        self.log = tk.Listbox(root, height=7, bg="#17171b", fg="#b9b9c0", bd=0,
                              font=("Consolas", 8))
        self.log.pack(fill="x", padx=10, pady=(6, 10))

        self.poll()

    # ---------------- Helfer ----------------
    def note(self, line):
        self.log.insert("end", line)
        self.log.see("end")
        while self.log.size() > 300:
            self.log.delete(0)

    def _busy(self):
        if self.running:
            messagebox.showinfo("Läuft gerade",
                                "Warte auf den aktuellen Lauf oder drücke STOP.")
            return True
        return False

    def _call(self, coro):
        if not self.client.loop_ref:
            messagebox.showinfo("Nicht verbunden", "Warte auf die Verbindung ...")
            return
        self.running = True
        asyncio.run_coroutine_threadsafe(coro, self.client.loop_ref)

    def _sel_ids(self, lb, shown):
        return [shown[n]["id"] for n in lb.curselection()]

    # ---------------- Tab 1 Aktionen ----------------
    def ch_all(self):
        if self.ch_lb.size():
            self.ch_lb.selection_set(0, "end")

    def ch_none(self):
        if self.ch_lb.size():
            self.ch_lb.selection_clear(0, "end")

    def ch_text(self):
        self.ch_lb.selection_clear(0, "end")
        for n, i in enumerate(self.shown_ch):
            if i["kind"] == "kanal" and i.get("sendable"):
                self.ch_lb.selection_set(n)

    def ro_all(self):
        if self.ro_lb.size():
            self.ro_lb.selection_set(0, "end")

    def ro_none(self):
        if self.ro_lb.size():
            self.ro_lb.selection_clear(0, "end")

    def do_server_name(self):
        if self._busy():
            return
        name = self.srv_entry.get().strip()
        if not name:
            messagebox.showinfo("Name fehlt", "Gib einen Servernamen ein.")
            return
        self.note("setze Server-Name ...")
        self._call(self.client.set_server_name(name))

    def do_rename_channels(self):
        if self._busy():
            return
        ids = self._sel_ids(self.ch_lb, self.shown_ch)
        name = self.ch_name.get().strip()
        if not ids or not name:
            messagebox.showinfo("Fehlt etwas",
                                "Kanäle markieren UND einen Namen eingeben.")
            return
        if self.opt_del.get():
            pass  # Warnung in Vorschau
        self.note("benenne %d Kanäle -> %r ..." % (len(ids), name))
        self._call(self.client.run_rename_channels(ids, name))

    def do_rename_roles(self):
        if self._busy():
            return
        ids = self._sel_ids(self.ro_lb, self.shown_ro)
        name = self.ro_name.get().strip()
        if not ids or not name:
            messagebox.showinfo("Fehlt etwas",
                                "Rollen markieren UND einen Namen eingeben.")
            return
        self.note("benenne %d Rollen -> %r ..." % (len(ids), name))
        self._call(self.client.run_rename_roles(ids, name))

    def do_rename_roles_all(self):
        if self._busy():
            return
        ids = [r["id"] for r in self.shown_ro if r["editable"]]
        name = self.ro_name.get().strip()
        if not ids or not name:
            messagebox.showinfo("Fehlt etwas",
                                "Erst Namen eingeben (nicht editierbare "
                                "Rollen werden übersprungen).")
            return
        self.note("benenne ALLE editierbaren Rollen (%d) -> %r ..."
                  % (len(ids), name))
        self._call(self.client.run_rename_roles(ids, name))

    # ---------------- Nuke ----------------
    def _nuke_any(self):
        return bool(self.opt_srv.get() or self.opt_del.get()
                    or self.opt_cre.get() or self.opt_post.get())

    def _gate(self):
        want = ""
        if self.data and "guild" in self.data:
            want = self.data["guild"]
        ok = (not self.running
              and self._nuke_any()
              and self.gate_ok.get() == 1
              and self.gate_entry.get().strip() == want
              and want != "")
        self.nuke_btn.config(state="normal" if ok else "disabled")
        # Kick-Tore
        kick_ready = (not self.running and self.kick_ok.get() == 1
                      and len(self.members) > 0)
        self.kick_sel_btn.config(state="normal" if kick_ready else "disabled")
        self.kick_all_btn.config(state="normal" if kick_ready else "disabled")

    def nuke_preview(self):
        if not self.data:
            return
        parts = []
        if self.opt_srv.get():
            parts.append("Server-Name -> %r" % self.nuke_srv.get().strip())
        if self.opt_del.get():
            k = len([c for c in self.data["channels"]])
            parts.append("LOESCHEN: %d Eintraege" % k)
        if self.opt_cre.get():
            parts.append("erstelle %s x %r"
                         % (self.nuke_cre_n.get(), self.nuke_cre_name.get().strip()))
        if self.opt_del.get() and self.opt_post.get():
            parts.append("poste in die NEUEN Kanaele")
        elif self.opt_post.get():
            parts.append("poste in alle sendbaren Kanaele")
        if self.opt_del.get() and self.opt_srv.get() is None:
            pass
        if self.opt_del.get() and not self.opt_srv.get():
            parts.append("Server-Name bleibt")
        self.note("VORSCHAU: " + (" | ".join(parts) if parts else "nichts gewählt")
                  + (" | Achtung: Loeschen ist Dauer!" if self.opt_del.get() else ""))

    def do_nuke(self):
        if self._busy():
            return
        opts = {
            "server_name": self.nuke_srv.get().strip() if self.opt_srv.get() else "",
            "delete": bool(self.opt_del.get()),
            "create_n": int(self.nuke_cre_n.get() or 0) if self.opt_cre.get() else 0,
            "create_name": self.nuke_cre_name.get().strip(),
            "rename": False, "rename_to": "",
            "post": bool(self.opt_post.get()),
            "post_text": self.nuke_post.get("1.0", "end").strip(),
        }
        if not (self.gate_ok.get() == 1
                and self.gate_entry.get().strip() == (self.data or {}).get("guild", "\x00")):
            messagebox.showinfo("Gesperrt", "Servername + Haeckchen noetig.")
            return
        self.note("NUKE gestartet ...")
        self._call(self.client.run_nuke(opts))

    # ---------------- Mitglieder ----------------
    def do_load_members(self):
        if self.running:
            return
        self.mem_lbl.config(text="lade ...")
        self._call(self.client.load_members())

    def _kick_ids(self, ids):
        out, skip = [], 0
        for i in ids:
            m = self.members[i]
            if m["owner"] or m["bot"]:
                skip += 1
                continue
            out.append(m["id"])
        if skip:
            self.note("%d übersprungen (Owner/Bot)" % skip)
        return out

    def do_kick_sel(self):
        if self._busy():
            return
        ids = self._kick_ids(list(self.mem_lb.curselection()))
        if not ids:
            messagebox.showinfo("Auswahl leer",
                                "Markiere Mitglieder in der Liste.")
            return
        reason = self.kick_reason.get().strip()
        self.note("kicke %d Mitglieder ..." % len(ids))
        self._call(self.client.run_kick(ids, reason))

    def do_kick_all(self):
        if self._busy():
            return
        ids = self._kick_ids(list(range(len(self.members))))
        if not ids:
            return
        if not messagebox.askyesno(
                "Alle kicken?",
                "Wirklich %d geladene Mitglieder kicken?\n\n"
                "Owner und Bots bleiben verschont. Zurueck nur ueber "
                "Einladung." % len(ids)):
            return
        reason = self.kick_reason.get().strip()
        self.note("kicke ALLE (%d) ..." % len(ids))
        self._call(self.client.run_kick(ids, reason))

    # ---------------- Diverses ----------------
    def do_stop(self):
        self.client.stop_flag = True
        self.note("STOP angefordert ...")

    def do_refresh(self):
        if self.client.loop_ref:
            asyncio.run_coroutine_threadsafe(self.client.refresh(),
                                             self.client.loop_ref)

    def _fill_status(self, d):
        self.st_txt.configure(state="normal")
        self.st_txt.delete("1.0", "end")
        if "error" in d:
            self.st_txt.insert("end", d["error"] + "\n")
        else:
            yn = lambda b: "OK  " if b else "FEHLT"
            c = d["can"]
            lines = [
                "Bot        : %s" % d["user"],
                "Server     : %s (ID %d)" % (d["guild"], d["gid"]),
                "Mitglieder : %s" % d["members"],
                "Bot-Top    : %s (pos %d)" % (d["top_role"], d["top_pos"]),
                "Rollen     : %d | Kanaele/Ordner: %d" % (len(d["roles"]),
                                                          len(d["channels"])),
                "",
                "Rechte:",
                "  Server-Name aendern        : %s" % yn(c["server"]),
                "  Kanaele (u/l/erstellen)    : %s" % yn(c["kanal"]),
                "  Rollen umbenennen          : %s  (nur unterhalb Top-Rolle)"
                % yn(c["rolle"]),
                "  Mitglieder kicken          : %s" % yn(c["kick"]),
                "  Nicknames anderer aendern  : %s" % yn(c["nick"]),
                "  Einladung erstellen        : %s  (Vanity/Bestand wird "
                "trotzdem versucht)" % yn(c["invite"]),
                "  Nachrichten senden         : %s" % yn(c["send"]),
                "",
                "Members-Intent : siehe Tab Mitglieder (403 = fehlt, dann",
                "  Portal -> Applications -> Bot -> Privileged Gateway Intents",
                "  -> Server Members Intent AN)",
                "Kick fehlt?    : Servereinstellungen -> Integrationen ->",
                "  SPECTRE -> 'Mitglieder kicken' an -> Speichern",
                "  (und SPECTRE-Rolle ganz nach oben ziehen)",
                "Nick fehlt?    : gleicher Ort -> 'Nicknames verwalten' an,",
                "",
                "Backups: %s" % BACKUP_DIR,
            ]
            self.st_txt.insert("end", "\n".join(lines))
        self.st_txt.configure(state="disabled")

    def _fill_channels(self, d):
        self.ch_lb.delete(0, "end")
        self.shown_ch = d["channels"]
        for i in self.shown_ch:
            self.ch_lb.insert("end", i["label"])

    def _fill_roles(self, d):
        self.ro_lb.delete(0, "end")
        self.shown_ro = d["roles"]
        for i in self.shown_ro:
            self.ro_lb.insert("end", i["label"])

    # ---------------- Events ----------------
    def poll(self):
        try:
            while True:
                ev = self.q.get_nowait()
                kind = ev[0]
                if kind == "ready":
                    d = ev[1]
                    self.data = d
                    if "error" in d:
                        self.status_lbl.config(text=d["error"], fg="#ff6b6b")
                    else:
                        self._fill_status(d)
                        self._fill_channels(d)
                        self._fill_roles(d)
                        self.srv_entry.delete(0, "end")
                        self.srv_entry.insert(0, d["guild"])
                        self.gate_entry.delete(0, "end")
                        c = d["can"]
                        flags = "".join([
                            "Server" + ("✔" if c["server"] else "✘") + " ",
                            "Kanäle" + ("✔" if c["kanal"] else "✘") + " ",
                            "Rollen" + ("✔" if c["rolle"] else "✘") + " ",
                            "Kick" + ("✔" if c["kick"] else "✘") + " ",
                            "Nick" + ("✔" if c["nick"] else "✘"),
                        ])
                        self.status_lbl.config(
                            text="verbunden als %s | %s" % (d["user"], flags),
                            fg="#39d98a" if c["kick"] else "#ffd166")
                        self.note("verbunden: %d Kanäle, %d Rollen, %s Mitglieder"
                                  % (len(d["channels"]), len(d["roles"]),
                                     d["members"]))
                        self._gate()
                elif kind == "members":
                    _, members, err = ev
                    self.mem_lb.delete(0, "end")
                    self.members = members or []
                    for m in self.members:
                        tag = (" [OWNER]" if m["owner"] else
                               (" [BOT]" if m["bot"] else ""))
                        nm = m["name"]
                        if m.get("nick"):
                            nm += " (%s)" % m["nick"]
                        if m.get("top"):
                            nm += " | %s" % m["top"]
                        self.mem_lb.insert("end", nm + tag)
                    if err:
                        self.mem_lbl.config(text="FEHLER: " + err, fg="#ff6b6b")
                        self.note("Mitglieder: " + err)
                    else:
                        self.mem_lbl.config(text="%d geladen" % len(self.members),
                                            fg="#39d98a")
                        self.note("%d Mitglieder geladen" % len(self.members))
                    self.running = False
                    self._gate()
                elif kind == "prog":
                    _, sent, total, label = ev
                    self.bar.config(maximum=max(total, 1), value=sent)
                    self.prog_lbl.config(text="%d/%d" % (sent, total))
                    if sent == 0:
                        self.note("lauf: %s" % label)
                elif kind == "log":
                    self.note(ev[1])
                elif kind == "done":
                    _, op, sent, err = ev
                    self.note("FERTIG [%s]: %d ok, %d Fehler" % (op, sent, err))
                    self.running = False
                    if op == "server" and self.data:
                        self.data["guild"] = self.srv_entry.get().strip()
                    self._gate()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def main():
    token = load_token()
    events = queue.Queue()
    selftest = "--selftest" in sys.argv
    client = PanelClient(events, selftest=selftest)

    if selftest:
        try:
            asyncio.run(client.start(token))
        except discord.LoginFailure:
            print("LOGIN_BAD")
            return 2
        except Exception as e:
            print("FEHLER", type(e).__name__, str(e)[:160])
            return 1
        return 0

    def run_client():
        try:
            asyncio.run(client.start(token))
        except Exception:
            events.put(("log", "Verbindung beendet/Fehler"))

    threading.Thread(target=run_client, daemon=True).start()
    root = tk.Tk()
    App(root, events, client)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
