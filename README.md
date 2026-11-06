# JARVIS — shaxsiy avtonom AI agent

MacBook'da ishlaydigan, Telegram va ovoz orqali boshqariladigan shaxsiy agent.
To'liq arxitektura hujjati: https://claude.ai/artifact/H7X3huFsHAdmwjjtCYhhjc

## Hozirgi holat (0-bosqich: poydevor)

- `jarvis/security/policy.py` — Policy Gateway: terminal buyruqlarini R0–R4 darajalarga ajratadi, xavflilarini bloklaydi (`config/commands.yaml`).
- `jarvis/tools/registry.py` — Tool Registry va `@tool` dekoratori.
- `jarvis/tools/system.py` — `system.status`, `shell.run` (faqat Policy Gateway orqali).
- `jarvis/interfaces/api.py` — FastAPI: `/health`, `/tools`, `/policy/check`.
- `jarvis/interfaces/telegram_bot.py` — aiogram bot, faqat egasining xabarlarini qabul qiladi.
- `jarvis/voice/` — ovozni tushunish: lokal Whisper (`faster-whisper`), audio Mac'dan chiqmaydi.
  Telegram ovozli xabarlari, `jarvis-voice` (Mac mikrofoni) va `POST /voice/transcribe`.
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

## Ovoz

Ovoz moduli Mac'da native ishlaydi (Docker'da o'rnatilmaydi):

```bash
pip install -e ".[voice]"
jarvis-voice                    # Enter — gapirish, Enter — to'xtatish
jarvis-voice --language ru      # boshqa til
curl -F file=@ovoz.ogg http://127.0.0.1:8020/voice/transcribe
```

- Model: `JARVIS_STT_MODEL` (standart `large-v3-turbo`, ~1.6 GB, birinchi ishga tushirishda yuklanadi).
  Kuchsiz internet yoki tezlik kerak bo'lsa — `small`, lekin o'zbek tilida xato ko'payadi.
- Til: `JARVIS_STT_LANGUAGE` (standart `uz`; bo'sh qoldirilsa avtomatik aniqlanadi).
- Birinchi `jarvis-voice` ishga tushganda macOS Terminal'ga mikrofon ruxsatini so'raydi.
- Hozircha ovoz orqali faqat «holat» buyrug'i bajariladi; qolgan matn agent sikli ulanganda
  orkestratorga uzatiladi.

## CI/CD

`.github/workflows/ci.yml`: har push va PR'da `ruff` + `pytest`; `main`ga push bo'lganda Docker image
yig'iladi, `/health` smoke test o'tkaziladi va `ghcr.io/satorovramazonbek/ai_agent` ga yuklanadi.
