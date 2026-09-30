#!/usr/bin/env bash
# Install or upgrade the AI Usage plasmoid for the current user.
set -euo pipefail
cd "$(dirname "$0")"
ID=com.joegineered.aiusage
if [ -d "${XDG_DATA_HOME:-$HOME/.local/share}/plasma/plasmoids/$ID" ]; then
    kpackagetool6 -t Plasma/Applet -u package
else
    kpackagetool6 -t Plasma/Applet -i package
fi
echo "Installed. Add 'AI Usage' via panel → Add Widgets."
echo "After upgrades, restart plasmashell: systemctl --user restart plasma-plasmashell"
