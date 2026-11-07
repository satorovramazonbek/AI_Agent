# JARVIS — shaxsiy avtonom AI agent

MacBook'da ishlaydigan, Telegram va ovoz orqali boshqariladigan shaxsiy agent.
To'liq arxitektura hujjati: https://claude.ai/artifact/H7X3huFsHAdmwjjtCYhhjc

## Hozirgi holat (0-bosqich: poydevor)

- `jarvis/security/policy.py` — Policy Gateway: terminal buyruqlarini R0–R4 darajalarga ajratadi, xavflilarini bloklaydi (`config/commands.yaml`).
- `jarvis/tools/registry.py` — Tool Registry va `@tool` dekoratori.
- `jarvis/tools/system.py` — `system.status`, `shell.run` (faqat Policy Gateway orqali).
- `jarvis/interfaces/api.py` — FastAPI: `/health`, `/tools`, `/policy/check`, `/agent/ask`,
  `/voice/transcribe`.
- `jarvis/interfaces/telegram_bot.py` — aiogram bot, faqat egasining xabarlarini qabul qiladi.
- `jarvis/core/commands.py` — **bepul buyruqlar** (API'siz): dastur ochish/yopish, ovoz,
  soat/sana, batareya, ekranni qulflash, eslatmalar. O'zbek, rus (kirill ham) va ingliz tilida.
- `jarvis/tools/macos.py` — macOS amallari (`open`, `osascript`, `pmset`), shell'siz.
- `jarvis/core/agent.py` — agent sikli: Claude tool'larni (Tool Registry) chaqiradi,
  terminal buyruqlari Policy Gateway'dan o'tadi; xavfli buyruqlar bloklanadi yoki tasdiq kutadi.
- `jarvis/models/router.py` — Model Router: LLM chaqiruvlarining yagona nuqtasi.
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

## JARVIS.app — Mac ilovasi (tavsiya etiladi)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[voice,app]"
./scripts/build-app.sh        # ~/Applications/JARVIS.app ga o'rnatadi
open ~/Applications/JARVIS.app
```

- Menyu panelida (soat yonida) halqa belgisi chiqadi; Dock'da ko'rinmaydi.
- **🎙 Gapirish** — bir marta bosing va gapiring; jim qolsangiz yozish o'zi to'xtaydi.
  Javob bildirishnoma bo'lib keladi. **⌨️ Yozib buyruq berish** — matn bilan.
- API (`127.0.0.1:8020`, `JARVIS_APP_PORT`) va Telegram bot ilova ichida ishlaydi.
- Birinchi «Gapirish»da macOS mikrofon ruxsatini so'raydi — «JARVIS» uchun ruxsat bering.
- Mac yonganda ochilishi uchun: System Settings → General → Login Items → «+» → JARVIS.
- Log: `~/Library/Logs/jarvis/app.log`. Kod o'zgarsa qayta yig'ish shart emas — ilovani
  qayta ochish kifoya (ilova loyiha papkasidagi `.venv` dan ishlaydi).

## Fon xizmati (ilovasiz variant)

> JARVIS.app ishlatsangiz, bu xizmat kerak emas (ikkalasi ham 8020-portni ishlatadi).

```bash
./scripts/install-launchd.sh     # o'rnatish va ishga tushirish (port 8020)
tail -f ~/Library/Logs/jarvis/jarvis.log
./scripts/uninstall-launchd.sh   # to'xtatish va o'chirish
```

Xizmat `.venv` va loyiha papkasidagi `.env` ni ishlatadi; `.env` o'zgarsa, o'rnatish skriptini
qayta ishga tushiring.

## Ovoz

**Tezkor va salqin rejim (Apple Silicon, tavsiya etiladi):** Whisper grafik yadrolarda (MLX):
bitta buyruq ~1 s, protsessor deyarli band bo'lmaydi (CT2 da ~5 s va ~4 yadro).

```bash
.venv/bin/python scripts/convert_mlx.py   # o'zbekcha modelni MLX'ga o'giradi (~1.6 GB, bir marta)
```

Model bo'lsa JARVIS uni avtomatik ishlatadi (`JARVIS_STT_ENGINE=auto`); bo'lmasa CT2 (CPU).

Ovoz moduli Mac'da native ishlaydi (Docker'da o'rnatilmaydi):

```bash
pip install -e ".[voice]"
jarvis-voice                    # Enter — gapirish, Enter — to'xtatish
jarvis-voice --language ru      # boshqa til
curl -F file=@ovoz.ogg http://127.0.0.1:8020/voice/transcribe
```

- Model: `JARVIS_STT_MODEL` — standart **o'zbek tiliga o'rgatilgan** `large-v3-turbo`
  (`hostmepanda/whisper-large-v3-turbo-uzbek-ct2`, MIT, ~1.6 GB, bir marta yuklanadi).
  Haqiqiy yozuvda asl model «oktanga salon de bibor», o'zbekchasi «o'ktamga salom deb yubor»
  deb eshitdi. Asl model kerak bo'lsa: `large-v3-turbo` (+ `JARVIS_STT_USE_HINTS=true`).
- Til: `JARVIS_STT_LANGUAGE` (standart `uz`; bo'sh qoldirilsa avtomatik aniqlanadi).
- Birinchi `jarvis-voice` ishga tushganda macOS Terminal'ga mikrofon ruxsatini so'raydi.
- Tanilgan matn avval bepul buyruqlarga solishtiriladi (pastdagi jadval); mos kelmasa va
  `ANTHROPIC_API_KEY` bo'lsa — agentga uzatiladi.

## Bepul buyruqlar (API kerak emas)

| Aytasiz | Bajariladi |
|---|---|
| «Safari'ni och», «brauzerni ochib ber», «Открой телеграм» | dastur ochiladi |
| «Telegram'ni yop», «Закрой калькулятор» | dastur yopiladi |
| «Ovozni ko'tar / pasaytir / o'chir / yoq», «Ovozni 40 ga qo'y», «Громче» | ovoz |
| «Soat necha?», «Bugun nechanchi?», «Сколько времени?» | vaqt / sana |
| «Batareya qancha?», «Kompyuter holati» | batareya / tizim |
| «Ekranni qulfla» | ekran o'chadi |
| «Eslatma: non olish», «Eslatmalarimni o'qi» | eslatma yoziladi / o'qiladi |
| «Obsidianni och va yozib qo'y: …», «Obsidian'ga yoz: …», «Запиши в обсидиан …» | Obsidian'ga yoziladi va ochiladi |
| «Nima qila olasan?» | buyruqlar ro'yxati |

Buyruq tanilmasa va `ANTHROPIC_API_KEY` bo'lsa, gap agentga uzatiladi; kalit bo'lmasa JARVIS
buyruqlar ro'yxatini ko'rsatadi.

Eslatmalar Obsidian vault'ida saqlanadi: `<vault>/JARVIS/Eslatmalar.md` (vault Obsidian
sozlamalaridan avtomatik topiladi; boshqasi kerak bo'lsa — `JARVIS_OBSIDIAN_VAULT`). Obsidian
bo'lmasa — `~/Documents/JARVIS/eslatmalar.md`. Boshqa fayl uchun — `JARVIS_NOTES_FILE`.

Dastur yopishda macOS bir marta «boshqarishga ruxsat» so'raydi.

## Telegram'ga xabar (API'siz)

«Telegramni ochib Aliga salom deb yubor» → JARVIS Telegram'ni ochadi, qidiruvga ismni yozadi,
birinchi natijani ochadi va xabarni **qoralama** qilib yozadi. Ochilgan chat nomi va xabar
ko'rsatiladi; «ha» (yoki tugma) bosilgandagina Enter bosiladi. Ochilgan chat ism bilan mos
kelmasa — ogohlantiradi. Boshqaruv paytida ekranda «🤖 JARVIS boshqaryapti» yozuvi va to'q
sariq hoshiya turadi.

Bir martalik: System Settings → Privacy & Security → **Accessibility** → JARVIS ni yoqing.
Ixtiyoriy (ekransiz): `.env` ga my.telegram.org dan `JARVIS_TG_API_ID/HASH`, keyin
`.venv/bin/jarvis-telegram-login`.

## Saqlangan joylar (telefondan)

Telegram bot orqali (BotFather tokeni — bepul): telefonda «Turgan joyimni Pismadonchani uyi deb
saqla» deng (yoki ovozli xabar) → «📍 Joylashuvni yuborish» tugmasini bosing → saqlanadi.
Yoki avval lokatsiya yuboring, keyin nomini ayting. «Pismadonchani uyiga yo'l ko'rsat» → bot
lokatsiya pini va 🧭 Google Maps / Yandex / Apple Maps tugmalarini yuboradi — bosib, «Start».
Joylar: `~/Library/Application Support/JARVIS/places.json` va Obsidian'da `JARVIS/Joylar.md`.

## Agent (ixtiyoriy, pullik)

```bash
curl -s http://127.0.0.1:8020/agent/ask -H 'content-type: application/json' \
  -d '{"text": "Diskda qancha joy qoldi?"}'
```

- Model: `JARVIS_MODEL` (standart `claude-opus-5-5`), chuqurlik: `JARVIS_MODEL_EFFORT`.
- Rad etilgan so'rovlar uchun serverdagi zaxira model yoqilgan (`fallbacks: "default"`).
- Suhbat xotirasi sessiya bo'yicha (Telegram chat, `mic`, `api`) — 30 daqiqa jimlikdan keyin
  yangilanadi. Testlar haqiqiy API'ni hech qachon chaqirmaydi.

## CI/CD

`.github/workflows/ci.yml`: har push va PR'da `ruff` + `pytest`; `main`ga push bo'lganda Docker image
yig'iladi, `/health` smoke test o'tkaziladi va `ghcr.io/satorovramazonbek/ai_agent` ga yuklanadi.
