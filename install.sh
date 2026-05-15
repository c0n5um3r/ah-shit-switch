#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(dirname "$(realpath "$0")")

for cmd in wtype hyprctl python3; do
    command -v "$cmd" &>/dev/null || { echo "ERROR: $cmd not found"; exit 1; }
done
python3 -c "import evdev" 2>/dev/null \
    || { echo "ERROR: python-evdev missing — sudo pacman -S python-evdev"; exit 1; }

sudo install -m755 "$SCRIPT_DIR/ah_shit_switch.py" /usr/local/bin/ah-shit-switch

SERVICE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$SERVICE_DIR"
install -m644 "$SCRIPT_DIR/ah-shit-switch.service" "$SERVICE_DIR/"

if ! groups | grep -qw input; then
    echo "Adding $USER to input group (re-login required)"
    sudo usermod -aG input "$USER"
fi

systemctl --user daemon-reload
systemctl --user enable --now ah-shit-switch
echo "Done. Status: systemctl --user status ah-shit-switch"
