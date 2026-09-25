# SPECTRE DC Bot

Discord-Bot + Server-Terminal (SPECTRE v2.7) – Steuerung des eigenen Servers
über Tastatur und Discord-Befehle.

## Dateien

| Datei              | Was es ist                                          |
|--------------------|-----------------------------------------------------|
| `bot_cli.py`       | **SPECTRE Bot-Terminal** – Startdatei (Doppelklick) |
| `discord_bot.py`   | Discord-Befehle (`!ping`, `!hilfe`, `!spam`, …)     |
| `server_panel.py`  | API-/Panel-Client (Rollen, Kanaele, Server-Infos)   |
| `lookup_tool.py`   | Lookup-Kernmodul (Nur-Lese-Abfragen)                |
| `lookup_cli.py`    | Terminal-Renderer/Menu fuer die Abfragen            |

## Setup

1. `pip install discord.py aiohttp`
2. `bot_config.example.json` als `bot_config.json` kopieren
3. Bot-Token eintragen (https://discord.com/developers/applications → Bot → Reset Token)
4. `python bot_cli.py`

## Sicherheit

- `bot_config.json` mit dem echten Token gehoert **nie** ins Repository
  (steht in `.gitignore`).
- Token niemals in Chats, Screenshots oder Issues posten.
- Bei Leak sofort **Reset Token** bei Discord und neu eintragen.

## Regeln

- Nur fuer den **eigenen Server** nutzen.
- Deckel: 1000 Nachrichten pro Lauf, NUKE braucht Bestaetigungswort,
  Strg+C stoppt sofort.
- Kein Undo – Backups liegen lokal in `LookupTool/backups`.
