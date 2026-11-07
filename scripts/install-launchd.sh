#!/bin/zsh
# JARVIS'ni macOS fon xizmati (launchd) sifatida o'rnatadi: Mac yonganda o'zi ishga tushadi,
# yiqilsa qayta ko'tariladi. O'chirish: scripts/uninstall-launchd.sh
set -euo pipefail

LABEL="com.jarvis.agent"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS="$HOME/Library/Logs/jarvis"
PORT="${JARVIS_PORT:-8020}"   # Docker'dagi JARVIS 8010 da, shuning uchun bu yerda 8020

if [[ ! -x "$PY" ]]; then
  echo "Avval muhitni yarating: python3 -m venv .venv && .venv/bin/pip install -e '.[voice]'" >&2
  exit 1
fi
[[ -f "$ROOT/.env" ]] || echo "Ogohlantirish: .env yo'q — agent va Telegram o'chiq bo'ladi (cp .env.example .env)."

mkdir -p "$LOGS" "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>-m</string><string>jarvis.main</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>JARVIS_PORT</key><string>$PORT</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOGS/jarvis.log</string>
  <key>StandardErrorPath</key><string>$LOGS/jarvis.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

for _ in {1..20}; do
  curl -fs "http://127.0.0.1:$PORT/health" >/dev/null && break
  sleep 1
done
if curl -fs "http://127.0.0.1:$PORT/health" >/dev/null; then
  echo "✅ JARVIS ishlayapti: http://127.0.0.1:$PORT  (log: $LOGS/jarvis.log)"
else
  echo "❌ JARVIS javob bermadi — logni ko'ring: tail -50 $LOGS/jarvis.log" >&2
  exit 1
fi
