#!/bin/zsh
# JARVIS.app ni yig'adi va ~/Applications ga qo'yadi (Launchpad va Spotlight'da chiqadi).
#   ./scripts/build-app.sh            # yig'ish + o'rnatish
#   ./scripts/build-app.sh --no-install
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/dist/JARVIS.app"
DEST="$HOME/Applications/JARVIS.app"
PY="$ROOT/.venv/bin/python"

[[ -x "$PY" ]] || { echo "Avval: python3 -m venv .venv && .venv/bin/pip install -e '.[voice,app]'" >&2; exit 1; }
"$PY" -c "import rumps, faster_whisper, sounddevice, ApplicationServices, Quartz" 2>/dev/null \
  || "$ROOT/.venv/bin/pip" install -q -e "$ROOT[voice,app]"

echo "→ belgilar"
"$PY" "$ROOT/scripts/make_icons.py"

echo "→ ilova tuzilmasi"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
clang -O2 -Wall -o "$APP/Contents/MacOS/JARVIS" "$ROOT/scripts/launcher.c"
iconutil -c icns "$ROOT/build/JARVIS.iconset" -o "$APP/Contents/Resources/JARVIS.icns"
print -r -- "$ROOT" > "$APP/Contents/Resources/root"

VERSION="$("$PY" -c 'import jarvis; print(jarvis.__version__)')"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>JARVIS</string>
  <key>CFBundleDisplayName</key><string>JARVIS</string>
  <key>CFBundleIdentifier</key><string>com.jarvis.app</string>
  <key>CFBundleExecutable</key><string>JARVIS</string>
  <key>CFBundleIconFile</key><string>JARVIS</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>JARVIS ovozli buyruqlaringizni eshitishi uchun mikrofon kerak. Ovoz Mac'dan chiqmaydi.</string>
  <key>NSAppleEventsUsageDescription</key>
  <string>JARVIS siz aytgan dasturlarni yopishi va ovozni boshqarishi uchun.</string>
</dict>
</plist>
EOF

# Ad-hoc imzo: macOS mikrofon ruxsatini qayta yig'ishlar orasida ham eslab qolishi uchun.
codesign --force --sign - --identifier com.jarvis.app "$APP"
echo "✅ Yig'ildi: $APP"

if [[ "${1:-}" != "--no-install" ]]; then
  mkdir -p "$HOME/Applications"
  rm -rf "$DEST"
  cp -R "$APP" "$DEST"
  echo "✅ O'rnatildi: $DEST  (Launchpad / Spotlight → «JARVIS»)"
fi
