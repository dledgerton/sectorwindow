#!/bin/zsh
# Installs a weekly macOS check (Mondays 1:15 pm) that posts a notification when new data is published.
# Undo with: launchctl unload ~/Library/LaunchAgents/com.sectorwindow.freshness.plist && rm ~/Library/LaunchAgents/com.sectorwindow.freshness.plist
set -euo pipefail
ROOT="${0:A:h}/../.."; ROOT="${ROOT:A}"
PLIST="$HOME/Library/LaunchAgents/com.sectorwindow.freshness.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.sectorwindow.freshness</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string>
    <string>$ROOT/scripts/ops/check_freshness.py</string>
    <string>--notify</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StartCalendarInterval</key><dict>
    <key>Weekday</key><integer>1</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>15</integer>
  </dict>
  <key>StandardOutPath</key><string>$ROOT/logs/freshness.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/freshness.log</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed. Runs Mondays at 1:15 pm; if the Mac is asleep it runs when it wakes. Log: $ROOT/logs/freshness.log"
