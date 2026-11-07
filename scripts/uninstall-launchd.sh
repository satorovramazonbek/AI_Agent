#!/bin/zsh
# JARVIS fon xizmatini to'xtatadi va o'chiradi (loglar saqlanib qoladi).
set -euo pipefail

LABEL="com.jarvis.agent"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "JARVIS xizmati o'chirildi."
