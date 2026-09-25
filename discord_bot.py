# -*- coding: utf-8 -*-
"""
SPECTRE Discord-Bot (v2.7) - EIGENER Bot mit eigenem Token.
Befehle: !ping !hilfe !snap !account !ip !dns !mail !wetter !krypto
         !hn !sage <text> !spam <anzahl> <text> !kanal
         Server aendern (Verwalten-Recht, nur eigener Server):
         !servername !kneu !kvoice !kren !kweg !kcat !rolle
         !nuke (alle Kanale umbenennen / Nachricht in alle Kanaele)
Terminal: Text eingeben + Enter = Nachricht in den Zielkanal
          (Start: Automatik, Wechsel in Discord: !kanal),
          /spam [ <anzahl> <text> ] = Nachricht N-mal senden (ohne
          Argumente fragt der Bot nach Anzahl und Text, max 1000,
          volles Tempo - Discord drosselt selbst am Rate-Limit),
          /quit = Bot beenden.

Nur der EIGENE Bot-Token (discord.com/developers/applications -> Bot ->
Reset Token) wird verwendet. NIEMALS den Token eines Benutzerkontos
eingeben - Selfbots sperren das Konto, das ist auch gegen Discord-AGB.
Der Token liegt lokal in bot_config.json und wird nie geteilt/geloggt.
Lookups bleiben Nur-Lese; gesendet wird nur in den eigenen Server.
"""
import asyncio
import getpass
import json
import logging
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lookup_tool as core
import lookup_cli as cli

CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "bot_config.json")
_PREFIX = "!"
_MAX_SPAM = 1000  # harte Obergrenze pro Lauf (Unfall-Schutz)


def _load_cfg():
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"token": "", "channel": ""}


def _save_cfg(cfg):
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception:
        return False


def _setup():
    """Token/Channel einrichten (einmalig) -> (token, cfg) oder (None, cfg)."""
    cfg = _load_cfg()
    if cfg.get("token"):
        return cfg["token"], cfg
    print()
    print(cli.WARN + "  DISCORD-BOT SETUP (einmalig)" + cli.R)
    print(cli.GRAY + "  1. https://discord.com/developers/applications" + cli.R)
    print(cli.GRAY + "     -> New Application -> Bot -> Reset Token" + cli.R)
    print(cli.GRAY + "  2. Bot-Token kopieren - NIEMALS teilen!" + cli.R)
    print(cli.GRAY + "  3. Privileged Gateway Intents ->" + cli.R)
    print(cli.GRAY + "     MESSAGE CONTENT INTENT einschalten" + cli.R)
    print(cli.GRAY + "  4. OAuth2 -> URL Generator: scope 'bot'," + cli.R)
    print(cli.GRAY + "     Rechte: Send Messages, Embed Links," + cli.R)
    print(cli.GRAY + "     Manage Server / Channels / Roles ->" + cli.R)
    print(cli.GRAY + "     Link oeffnen -> Bot in den EIGENEN Server" + cli.R)
    print(cli.GRAY + "     einladen (Bot-Rolle nach oben schieben)" + cli.R)
    print()
    if not sys.stdin.isatty():
        # WICHTIG: getpass liest an der Konsole und BLOECKT, wenn stdin
        # eine Pipe ist - hier vorher abbrechen statt haengen zu bleiben.
        print("   " + cli.RED + "kein interaktives Terminal (Pipe) - "
              "Token-Abfrage ausgelassen" + cli.R)
        print("   " + cli.GRAY + "loesung: im echten Terminal starten "
              "oder bot_config.json anlegen" + cli.R)
        return None, cfg
    try:
        token = getpass.getpass("   Bot-Token: ").strip()
    except Exception:
        try:
            token = input("   Bot-Token: ").strip()
        except (EOFError, KeyboardInterrupt):
            token = ""
    if not token:
        print("   " + cli.RED + "kein Token - Bot-Setup abgebrochen" + cli.R)
        return None, cfg
    if token.count(".") != 2:
        print("   " + cli.RED + "sieht nicht nach einem BOT-Token aus"
              + cli.R)
        print("   " + cli.GRAY + "erwartet: 3 Teile mit 2 Punkten "
              "(Developer Portal -> Bot -> Reset Token). "
              "Benutzertoken = Selfbot = Sperrgefahr." + cli.R)
        return None, cfg
    cfg["token"] = token
    if not cfg.get("channel"):
        try:
            cfg["channel"] = input(
                "   Standard-Channel (Name, Enter = spaeter per !kanal): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            cfg["channel"] = ""
    if _save_cfg(cfg):
        print("   " + cli.GREEN + "gespeichert in bot_config.json - "
              + "Datei NIEMALS teilen oder hochladen" + cli.R)
    else:
        print("   " + cli.RED + "Konfig nicht speicherbar - Token gilt "
              + "nur fuer diese Sitzung" + cli.R)
    return token, cfg


def _run(fn, q=None):
    """Kern-/CLI-Funktion ansprechbar machen -> (pairs, fehler)."""
    try:
        res = fn(q) if q is not None else fn()
    except Exception as e:
        return None, str(e)
    if isinstance(res, tuple) and len(res) == 2 and res[0] is None:
        return None, str(res[1])
    pairs = res[0] if isinstance(res, tuple) else res
    if pairs is None:
        return None, "kein Ergebnis"
    return pairs, None


def _fmt(pairs, err=None):
    if err:
        return f"**Fehler:** {err}"
    lines = []
    for k, v in pairs:
        if v is None:
            v = "-"
        lines.append(f"**{k}:** {v}")
    txt = "\n".join(lines)
    if len(txt) > 1900:
        txt = txt[:1900] + "\n…"
    return txt


async def _spam_send(channel, text, count, on_progress=None):
    """Text N-mal SO SCHNELL WIE DISCORD ERLAUBT senden: keine
    kuenstliche Pause - discord.py drosselt selbst am Rate-Limit
    (ca. 5 Nachrichten alle 5 s pro Kanal), HTTP 429 wird von der
    Bibliothek ausgesetzt und danach sofort weitergegangen.
    on_progress(sent, total) laeuft alle 100 Nachrichten und am Ende."""
    sent = failed = total = 0
    for _ in range(count):
        try:
            await channel.send(text[:1900])
            sent += 1
        except Exception:
            failed += 1
            await asyncio.sleep(0.2)   # Fehlerschleife nicht hot-spin
        total += 1
        if on_progress and total % 100 == 0:
            try:
                on_progress(sent, count)
            except Exception:
                pass
    if on_progress:
        try:
            on_progress(sent, count)
        except Exception:
            pass
    return sent, failed


def _spam_parse(line, stdin):
    """/spam-Argumente holen: '<anzahl> <text>' oder interaktiv nachfragen.
    Die Anzahl kann direkt eingegeben werden - sonst fragt der Bot nach."""
    parts = line.split(maxsplit=2)

    def ask(prompt_txt):
        try:
            print("   " + prompt_txt, end="", flush=True)
            return stdin.readline().rstrip("\n")
        except Exception:
            return ""

    count = text = None
    if len(parts) >= 3 and parts[1].lstrip("-+").isdigit():
        count, text = int(parts[1]), parts[2]
    elif len(parts) == 2 and parts[1].lstrip("-+").isdigit():
        count = int(parts[1])
        text = ask("Nachricht: ")
    elif len(parts) == 2:
        text = parts[1]
        raw = ask("Wie oft? (1-1000): ").strip()
        count = int(raw) if raw.lstrip("-+").isdigit() else None
    else:
        raw = ask("Wie oft? (1-1000): ").strip()
        count = int(raw) if raw.lstrip("-+").isdigit() else None
        text = ask("Nachricht: ")
    if not count or not text:
        return None, None
    return max(1, min(count, _MAX_SPAM)), text


def _build(cfg):
    try:
        import discord
        from discord.ext import commands
    except ImportError:
        print("   " + cli.RED + "discord.py fehlt - installation:" + cli.R)
        print("   " + cli.GRAY + "pip install discord.py" + cli.R)
        return None

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix=_PREFIX, intents=intents,
                       help_command=None)
    # INFO-Gerede von discord.py/aiohttp unterdruecken - erst NACH dem
    # Bot-Bau, weil discord.py dort das Log-Level setzt. Ab WARNING
    # bleiben Warnungen und Fehler weiterhin sichtbar.
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    bot._spec_channel = None
    bot._spec_cfg = cfg
    bot._spec_loop = None
    bot._spec_ready = False

    def _target(bot):
        return getattr(bot, "_spec_channel", None)

    async def _reply(ctx, fn, q=None):
        async with ctx.typing():
            pairs, e = await asyncio.to_thread(_run, fn, q)
        await ctx.send(_fmt(pairs, e))

    @bot.event
    async def on_ready():
        bot._spec_loop = asyncio.get_running_loop()
        if bot._spec_ready:
            return
        bot._spec_ready = True
        try:
            await bot.change_presence(activity=discord.Game(
                name=f"SPECTRE v{cli.VER} | {_PREFIX}hilfe"))
        except Exception:
            pass
        gnames = ", ".join(g.name for g in bot.guilds) or "(kein Server)"
        # Kanal aus Config aufloesen
        want = (bot._spec_cfg or {}).get("channel", "").strip().lstrip("#")
        if want:
            for g in bot.guilds:
                ch = discord.utils.get(g.text_channels, name=want)
                if ch is None and want.isdigit():
                    ch = g.get_channel(int(want))
                if ch:
                    bot._spec_channel = ch
                    break
        # Automatik: ohne konfigurierten Kanal beim Start einen
        # passenden Textkanal waehlen (allgemein/general/chat zuerst)
        if bot._spec_channel is None:
            for g in bot.guilds:
                def _ok(c, g=g):
                    try:
                        p = c.permissions_for(g.me)
                        return p.send_messages and not c.is_news()
                    except Exception:
                        return False
                cand = [c for c in sorted(g.text_channels,
                                           key=lambda x: x.position)
                        if _ok(c)]
                if cand:
                    pref = [c for c in cand if c.name.lower()
                            in ("allgemein", "general", "chat")]
                    bot._spec_channel = pref[0] if pref else cand[0]
                    break
        ch = _target(bot)
        auto = not want
        print("   " + cli.GREEN + "BOT EINGELOGGT: "
              + str(bot.user) + cli.R)
        print("   " + cli.GRAY + "Server: " + gnames + cli.R)
        if ch:
            print("   " + cli.GRAY + "Zielkanal: #"
                  + str(getattr(ch, "name", ch))
                  + (" (Automatik)" if auto else "")
                  + " - wechsel: in Discord "
                  + f"{_PREFIX}kanal tippen" + cli.R)
        else:
            print("   " + cli.RED + "Zielkanal: keiner - tipp in Discord "
                  + f"{_PREFIX}kanal in den Wunschkanal" + cli.R)
        print("   " + cli.CYAN + "Los: Text + Enter = Nachricht in "
              "Discord | /spam <n> <text> | /quit = Ende" + cli.R)
        print()

    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Fehlt ein Argument: {_PREFIX}hilfe")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"Zahl erwartet, z.B. `{_PREFIX}spam 5 text` "
                           f"oder {_PREFIX}hilfe")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("Dafuer fehlt DIR die Discord-Berechtigung: "
                           + ", ".join(error.missing_permissions))
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("Dem BOT fehlt das Recht dafuer - im "
                           "OAuth2-Rechte-Haken: Server/Kanaele/Rollen "
                           "verwalten, dann Bot neu einladen.")
        elif isinstance(error, commands.CommandNotFound):
            pass
        else:
            try:
                await ctx.send(f"Fehler: {error}")
            except Exception:
                pass

    @bot.command(name="ping")
    async def cmd_ping(ctx):
        await ctx.send(f"Pong! {round(bot.latency * 1000)} ms")

    @bot.command(name="hilfe")
    async def cmd_hilfe(ctx):
        await ctx.send(
            "**SPECTRE-Bot - Befehle**\n"
            f"`{_PREFIX}ping` Latenz\n"
            f"`{_PREFIX}snap <name>` oeffentliches Snapchat-Profil\n"
            f"`{_PREFIX}account <name>` 9 Plattformen parallel\n"
            f"`{_PREFIX}ip <ip>` Geo-Daten\n"
            f"`{_PREFIX}dns <domain>` DNS-Eintraege\n"
            f"`{_PREFIX}mail <adresse>` MX/SPF/Domain-Check\n"
            f"`{_PREFIX}wetter <stadt>` Wetterdaten\n"
            f"`{_PREFIX}krypto` Top-Muenzen\n"
            f"`{_PREFIX}hn` Hacker-News Top 7\n"
            f"`{_PREFIX}sage <text>` Bot sendet deinen Text\n"
            f"`{_PREFIX}spam <anzahl> <text>` denselben Text N-mal "
            f"(max {_MAX_SPAM}, volles Tempo - Discord drosselt selbst)\n"
            f"`{_PREFIX}kanal` Zielkanal fuers Terminal-Senden merken\n"
            "**Server aendern** (nur mit Verwalten-Recht, nur der "
            "eigene Server):\n"
            f"  `{_PREFIX}servername <name>` Server umbenennen\n"
            f"  `{_PREFIX}kneu <name>` Textkanal · "
            f"`{_PREFIX}kvoice <name>` Voicekanal\n"
            f"  `{_PREFIX}kcat <name>` Kategorie · "
            f"`{_PREFIX}rolle <name>` Rolle anlegen\n"
            f"  `{_PREFIX}kren <alt> <neu>` Kanal umbenennen · "
            f"`{_PREFIX}kweg <name>` loeschen (Systemkanal nicht)\n"
            f"  `{_PREFIX}nuke kanal <name>` ALLE Kanaele umbenennen · "
            f"`{_PREFIX}nuke spam <text>` Text in alle Kanaele\n"
            "_Lookups sind Nur-Lese (nur oeffentliche Daten)._")

    @bot.command(name="kanal")
    async def cmd_kanal(ctx):
        bot._spec_channel = ctx.channel
        await ctx.send(f"Zielkanal gespeichert: #{ctx.channel.name}")

    @bot.command(name="sage")
    async def cmd_sage(ctx, *, text: str):
        bot._spec_channel = ctx.channel
        await ctx.send(text[:1900])

    @bot.command(name="spam")
    async def cmd_spam(ctx, count: int, *, text: str):
        bot._spec_channel = ctx.channel
        if count < 1:
            await ctx.send("Anzahl muss mindestens 1 sein.")
            return
        capped = min(count, _MAX_SPAM)
        note = f" (Limit {_MAX_SPAM} pro Lauf)" if count > capped else ""
        prog = await ctx.send(
            f"Starte: `{capped}`x ...{note} - volles Tempo, Discord "
            "drosselt selbst (ca. 5 alle 5 s pro Kanal)")

        def _p(done, tot):
            if done >= tot:
                return
            try:
                asyncio.create_task(prog.edit(
                    content=f"Laeuft: `{done}/{tot}` gesendet ..."))
            except Exception:
                pass

        sent, failed = await _spam_send(ctx.channel, text, capped, _p)
        tail = f", {failed} Fehler" if failed else ""
        msg = f"Fertig: **{sent}** Nachrichten gesendet{tail}."
        try:
            await prog.edit(content=msg)
        except Exception:
            await ctx.send(msg)

    # ------------------------------------------- Server-Verwaltung
    # Wirken NUR im Server, in dem der Bot eingeladen ist, und nur
    # fuer Mitglieder mit der passenden Discord-Berechtigung
    # (Discord prueft das selbst ueber die Decorator).

    def _find_channel(guild, name):
        low = (name or "").strip().lower()
        for ch in guild.channels:
            if str(ch.name).lower() == low:
                return ch
        return None

    @bot.command(name="servername")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def cmd_servername(ctx, *, name: str):
        alt = ctx.guild.name
        await ctx.guild.edit(name=name[:100])
        await ctx.send(f"Server umbenannt: `{alt}` -> `{name[:100]}`")

    @bot.command(name="kneu")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_channels=True)
    async def cmd_kneu(ctx, *, name: str):
        ch = await ctx.guild.create_text_channel(name[:100])
        await ctx.send(f"Textkanal erstellt: {ch.mention}")

    @bot.command(name="kvoice")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_channels=True)
    async def cmd_kvoice(ctx, *, name: str):
        ch = await ctx.guild.create_voice_channel(name[:100])
        await ctx.send(f"Voicekanal erstellt: `{ch.name}`")

    @bot.command(name="kcat")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_channels=True)
    async def cmd_kcat(ctx, *, name: str):
        cat = await ctx.guild.create_category(name[:100])
        await ctx.send(f"Kategorie erstellt: `{cat.name}`")

    @bot.command(name="kren")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_channels=True)
    async def cmd_kren(ctx, old: str, *, new: str):
        ch = _find_channel(ctx.guild, old)
        if ch is None:
            await ctx.send(f"Kein Kanal namens `{old}` gefunden.")
            return
        vorher = ch.name
        await ch.edit(name=new[:100])
        await ctx.send(f"Umbenannt: `{vorher}` -> `{ch.name}`")

    @bot.command(name="kweg")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_channels=True)
    async def cmd_kweg(ctx, *, name: str):
        ch = _find_channel(ctx.guild, name)
        if ch is None:
            await ctx.send(f"Kein Kanal namens `{name}` gefunden.")
            return
        if ch.id == ctx.guild.system_channel_id:
            await ctx.send("Systemkanal bleibt verschont.")
            return
        tmp = ch.name
        await ch.delete(reason="SPECTRE-Befehl von " + str(ctx.author))
        await ctx.send(f"Kanal geloescht: `{tmp}`")

    @bot.command(name="rolle")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def cmd_rolle(ctx, *, name: str):
        r = await ctx.guild.create_role(name=name[:100])
        await ctx.send(f"Rolle erstellt: `{r.name}`")

    # --------------------------------------------- Nuke (Server-weit)
    # Nur eigener Server (guild_only), nur fuer Mitglieder mit
    # Verwalten-Recht, BOT-Rechte werden pro Kanal geprueft.
    # Es wird NUR umbenannt und gesendet - nichts geloescht,
    # keine Rollen-/Rechte-Aenderung, kein Kick/Ban.

    def _nuke_help():
        return ("**!nuke - Server-weite Aktionen** "
                "(nur eigener Server, nur mit Verwalten-Recht):\n"
                f"`{_PREFIX}nuke kanal <name>` ALLE Kanaele umbenennen\n"
                f"`{_PREFIX}nuke spam <nachricht>` Text in alle Kanaele\n"
                f"`{_PREFIX}nuke spam <anzahl> <text>` N-mal in alle "
                f"Kanaele (Gesamtdeckel {_MAX_SPAM})\n"
                f"`{_PREFIX}nuke` zeigt diese Hilfe\n"
                "Es wird nichts geloescht - nur umbenannt und "
                "gesendet; Discord-Ratenlimits gelten weiter.")

    @bot.command(name="nuke")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def cmd_nuke(ctx, mode: str = "", *, rest: str = ""):
        m = (mode or "").lower()
        if not m:
            await ctx.send(_nuke_help())
            return

        if m in ("kanal", "channel", "name", "umbenennen"):
            name = (rest or "").strip()
            if not name:
                await ctx.send(f"Syntax: `{_PREFIX}nuke kanal "
                               "<neuer-name>`")
                return
            total = len(ctx.guild.channels)
            status = await ctx.send(f"Benenne {total} Kanaele um ...")
            ok = fail = 0
            fail_names = []
            for ch in ctx.guild.channels:
                try:
                    await ch.edit(name=name[:100])
                    ok += 1
                except Exception:
                    fail += 1
                    fail_names.append(str(getattr(ch, "name", "?")))
                if (ok + fail) % 10 == 0 and ok + fail < total:
                    try:
                        # await statt create_task: Endmeldung kann
                        # sonst von einem Fortschritts-Update
                        # ueberschrieben werden (Race)
                        await status.edit(
                            content=f"Laeuft: {ok + fail}/{total} "
                                    "Kanaele ...")
                    except Exception:
                        pass
            msg = (f"Fertig: **{ok}/{total}** Kanaele heissen jetzt "
                   f"`{name[:100]}`")
            if fail:
                msg += (f", {fail} uebersprungen (Rechte): "
                        + ", ".join(fail_names[:5])
                        + (" ..." if fail > 5 else ""))
            try:
                await status.edit(content=msg)
            except Exception:
                await ctx.send(msg)
            return

        if m in ("spam", "text", "nachricht", "senden"):
            toks = (rest or "").split(maxsplit=1)
            count = 1
            text = rest or ""
            if toks and toks[0].lstrip("-+").isdigit():
                count = max(1, int(toks[0]))
                text = toks[1] if len(toks) > 1 else ""
            if not text.strip():
                await ctx.send(f"Syntax: `{_PREFIX}nuke spam "
                               f"<nachricht>` oder `{_PREFIX}nuke spam "
                               "<anzahl> <text>`")
                return
            chans = [c for c in ctx.guild.channels
                     if isinstance(c, discord.TextChannel)]
            if not chans:
                await ctx.send("Keine Textkanaele gefunden.")
                return
            per = max(1, min(count, _MAX_SPAM // max(1, len(chans))))
            note = (f" ({count}x pro Kanal -> {per}x gedrosselt, "
                    f"Gesamtdeckel {_MAX_SPAM})") if per < count else ""
            status = await ctx.send(
                f"Sende {per}x in {len(chans)} Kanaelen ...{note}")
            sent_t = fail_t = skip = 0
            for i, ch in enumerate(chans, 1):
                try:
                    perms = ch.permissions_for(ctx.guild.me)
                except Exception:
                    perms = None
                if perms is not None and not perms.send_messages:
                    skip += 1
                    continue
                s, f2 = await _spam_send(ch, text, per)
                sent_t += s
                fail_t += f2
                try:
                    # await statt create_task (Reihenfolge sichern)
                    await status.edit(
                        content=f"Laeuft: Kanal {i}/{len(chans)} - "
                                f"{sent_t} Nachrichten ...")
                except Exception:
                    pass
            msg = (f"Fertig: **{sent_t}** Nachrichten in "
                   f"{len(chans) - skip} Kanaelen")
            if fail_t:
                msg += f", {fail_t} Fehler"
            if skip:
                msg += f", {skip} Kanaele uebersprungen (Bot-Recht fehlt)"
            msg += " - Discord drosselt pro Kanal selbst."
            try:
                await status.edit(content=msg)
            except Exception:
                await ctx.send(msg)
            return

        await ctx.send(_nuke_help())

    @bot.command(name="snap")
    async def cmd_snap(ctx, name: str):
        await _reply(ctx, core.lookup_snapchat, name)

    @bot.command(name="account")
    async def cmd_account(ctx, name: str):
        await _reply(ctx, core.lookup_account_view, name)

    @bot.command(name="ip")
    async def cmd_ip(ctx, ip: str):
        await _reply(ctx, core.lookup_ip, ip)

    @bot.command(name="dns")
    async def cmd_dns(ctx, domain: str):
        await _reply(ctx, core.lookup_domain, domain)

    @bot.command(name="mail")
    async def cmd_mail(ctx, addr: str):
        await _reply(ctx, core.lookup_email, addr)

    @bot.command(name="wetter")
    async def cmd_wetter(ctx, *, stadt: str):
        await _reply(ctx, cli.lookup_weather, stadt)

    @bot.command(name="krypto")
    async def cmd_krypto(ctx):
        await _reply(ctx, cli.lookup_crypto)

    @bot.command(name="hn")
    async def cmd_hn(ctx):
        await _reply(ctx, cli.lookup_hackernews)

    # Channel merken, wenn jemand einen Lookup-Befehl nutzt
    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        if message.content.startswith(_PREFIX):
            bot._spec_channel = message.channel
        await bot.process_commands(message)

    return bot


def _stdin_loop(bot):
    """Terminal-Eingaben als Nachrichten in den Zielkanal senden."""
    try:
        for line in sys.stdin:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line.strip().lower() in ("/quit", "/exit", "/ende"):
                loop = getattr(bot, "_spec_loop", None)
                if loop:
                    asyncio.run_coroutine_threadsafe(bot.close(), loop)
                else:
                    os._exit(0)
                return
            loop = getattr(bot, "_spec_loop", None)
            ch = getattr(bot, "_spec_channel", None)
            if not loop or ch is None:
                print("   " + cli.GRAY + "Kein Zielkanal - tipp in "
                      + f"Discord {_PREFIX}kanal in den Wunschkanal"
                      + cli.R)
                continue
            if line.strip().lower().startswith("/spam"):
                count, text = _spam_parse(line, sys.stdin)
                if not count or not text:
                    print("   " + cli.RED + "Syntax: /spam <anzahl> "
                          "<nachricht> - abgebrochen" + cli.R)
                    continue
                def _p(done, tot):
                    print("   " + cli.GRAY
                          + f"[laeuft: {done}/{tot} ...]" + cli.R,
                          flush=True)
                fut = asyncio.run_coroutine_threadsafe(
                    _spam_send(ch, text, count, _p), loop)
                try:
                    sent, failed = fut.result(timeout=count * 3 + 60)
                    print("   " + cli.GREEN
                          + f"[gesendet: {sent}x auf #{ch.name}]"
                          + (f" ({failed} Fehler)" if failed else "")
                          + cli.R)
                except Exception as e:
                    print("   " + cli.RED + f"Spam fehlgeschlagen: {e}"
                          + cli.R)
                continue
            fut = asyncio.run_coroutine_threadsafe(ch.send(line[:1900]),
                                                   loop)
            try:
                fut.result(timeout=10)
                print("   " + cli.GREEN + f"[gesendet -> #{ch.name}]"
                      + cli.R)
            except Exception as e:
                print("   " + cli.RED + f"Senden fehlgeschlagen: {e}"
                      + cli.R)
    except Exception:
        pass


def run():
    """Bot starten (blockiert bis /quit oder Ctrl+C)."""
    token, cfg = _setup()
    if not token:
        return
    bot = _build(cfg)
    if bot is None:
        return
    print("   " + cli.CYAN + "Verbinde mich ..." + cli.R)
    t = threading.Thread(target=_stdin_loop, args=(bot,), daemon=True)
    t.start()
    try:
        bot.run(token, log_level=logging.WARNING)
    except KeyboardInterrupt:
        print()
    except Exception as e:
        msg = str(e)
        if "token" in msg.lower() or "Unauthorized" in msg:
            print("   " + cli.RED + "Login fehlgeschlagen - Token pruefen"
                  + cli.R)
            print("   " + cli.GRAY + "(Developer Portal -> Bot -> Reset "
                  "Token; alte Token sind tot)" + cli.R)
        else:
            print("   " + cli.RED + f"Bot-Fehler: {msg}" + cli.R)
    print("   " + cli.GRAY + "Bot beendet - zurueck im Menue" + cli.R)
