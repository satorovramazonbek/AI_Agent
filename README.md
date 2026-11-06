# JARVIS — shaxsiy avtonom AI agent

MacBook'da ishlaydigan, Telegram va ovoz orqali boshqariladigan shaxsiy agent.
To'liq arxitektura hujjati: https://claude.ai/artifact/H7X3huFsHAdmwjjtCYhhjc

## Hozirgi holat (0-bosqich: poydevor)

- `jarvis/security/policy.py` — Policy Gateway: terminal buyruqlarini R0–R4 darajalarga ajratadi, xavflilarini bloklaydi (`config/commands.yaml`).
- `jarvis/tools/registry.py` — Tool Registry va `@tool` dekoratori.
- `jarvis/tools/system.py` — `system.status`, `shell.run` (faqat Policy Gateway orqali).
- `jarvis/interfaces/api.py` — FastAPI: `/health`, `/tools`, `/policy/check`.
- `jarvis/interfaces/telegram_bot.py` — aiogram bot, faqat egasining xabarlarini qabul qiladi.
- Docker (`jarvis` + PostgreSQL/pgvector), GitHub Actions CI/CD.

## Ishga tushirish

```bash
cp .env.example .env          # Telegram token va ID'ni yozing
docker compose up -d --build
curl http://127.0.0.1:8010/health   # port: JARVIS_PORT (standart 8010)
```

Lokal (Docker'siz):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m jarvis.main         # port: JARVIS_PORT (standart 8010)
```

> Docker'dagi JARVIS ham 8010 ni egallaydi — ikkalasini birga ishlatsangiz,
> lokal uchun boshqa port bering: `JARVIS_PORT=8020 python -m jarvis.main`.

> Eslatma: Docker konteyneri Linux VM ichida ishlaydi, shuning uchun Mac'ni boshqaradigan
> tool'lar (dastur ochish, AppleScript, mikrofon) keyingi bosqichlarda Mac'da native ishga tushiriladi.
> Docker'da — API, Telegram bot va ma'lumotlar bazasi.

## CI/CD

`.github/workflows/ci.yml`: har push va PR'da `ruff` + `pytest`; `main`ga push bo'lganda Docker image
yig'iladi, `/health` smoke test o'tkaziladi va `ghcr.io/satorovramazonbek/ai_agent` ga yuklanadi.
