#!/bin/bash
# Groove Tracker setup script — the one command that installs everything.
#
# Automates: system packages (including everything discovered the hard way
# while building this — see docs/SETUP.md's troubleshooting appendix),
# enabling SPI, cloning the Waveshare e-Paper driver into the right place,
# creating the venv and installing Python dependencies, interactively
# collecting your AudD/DVinyl/Home Assistant configuration, setting up a
# Samba file share (with password), and installing (but not starting) the
# systemd service. Safe to re-run — skips steps that are already done
# rather than redoing them, and never overwrites values you've already set.
#
# What this still can't do for you, if you skip it when prompted (see the
# checklist this script prints at the end, and docs/SETUP.md for details):
#   - Physically wiring the display and audio tap
#   - Signing up for an AudD API token in the first place
#   - Creating the read-only MongoDB user on your DVinyl instance
#   - Creating a Home Assistant Long-Lived Access Token
#
# Run this from the project root: bash install.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_USER="$(whoami)"
cd "$PROJECT_ROOT"

echo "=== Groove Tracker setup ==="
echo "Project root: $PROJECT_ROOT"
echo "User:         $CURRENT_USER"
echo

if [ ! -f "requirements.txt" ]; then
    echo "ERROR: requirements.txt not found. Run this script from the groove-tracker project root."
    exit 1
fi

# Collects whatever the interactive steps below couldn't fill in, so the
# final summary only lists what's actually still needed instead of a
# static checklist regardless of what you just entered.
STILL_NEEDED=()

# Reads a key's current value out of an env file (empty if unset/missing).
get_env_var() {
    local key="$1" file="$2"
    [ -f "$file" ] || return 0
    grep "^${key}=" "$file" 2>/dev/null | head -1 | cut -d'=' -f2-
}

# Sets (or adds) a key in an env file. Uses Python rather than sed so
# values containing /, &, or other sed-special characters (very possible
# in a MongoDB URI or an API token) don't need any escaping.
set_env_var() {
    local key="$1" value="$2" file="$3"
    python3 - "$key" "$value" "$file" <<'PYEOF'
import sys
key, value, path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    lines = f.readlines()
found = False
for i, line in enumerate(lines):
    if line.startswith(key + "="):
        lines[i] = f"{key}={value}\n"
        found = True
        break
if not found:
    lines.append(f"{key}={value}\n")
with open(path, "w") as f:
    f.writelines(lines)
PYEOF
}

echo "--- Step 1/8: System packages ---"
sudo apt update
sudo apt install -y python3-pip python3-venv git \
    libopenjp2-7 libopenblas-dev portaudio19-dev libsndfile1 libfreetype6
echo

echo "--- Step 2/8: Enabling SPI ---"
if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_spi 0
    echo "SPI enabled."
else
    echo "raspi-config not found — skipping (enable SPI manually if this isn't a Raspberry Pi)."
fi
echo

echo "--- Step 3/8: Waveshare e-Paper driver ---"
if [ -d "waveshare_epd" ]; then
    echo "waveshare_epd/ already exists at the project root — skipping."
else
    # The full Waveshare e-Paper repo has 33,000+ files covering every
    # product they sell (STM32, Arduino, Jetson boards, etc.) -- a full
    # checkout can exhaust inodes or tmpfs space on a small SD card / low-RAM
    # board. Sparse + partial clone fetches only the one folder we need.
    # Cloned inside the project dir rather than /tmp, in case /tmp is
    # RAM-backed on this board.
    SPARSE_DIR="$PROJECT_ROOT/.waveshare-sparse-clone"
    rm -rf "$SPARSE_DIR"
    echo "Cloning just the driver folder (sparse checkout, this may take a minute)..."
    git clone --filter=blob:none --sparse --depth 1 https://github.com/waveshare/e-Paper.git "$SPARSE_DIR"
    (cd "$SPARSE_DIR" && git sparse-checkout set RaspberryPi_JetsonNano/python/lib/waveshare_epd)
    cp -r "$SPARSE_DIR/RaspberryPi_JetsonNano/python/lib/waveshare_epd" "$PROJECT_ROOT/"
    rm -rf "$SPARSE_DIR"
    echo "Copied waveshare_epd/ to the project root."
fi
echo

echo "--- Step 4/8: Python virtual environment ---"
if [ -d "venv" ]; then
    echo "venv/ already exists — skipping creation."
else
    python3 -m venv venv
    echo "Created venv/."
fi

echo "Installing Python dependencies (this can take a few minutes on a Pi Zero)..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
echo

echo "--- Step 5/8: Environment file ---"
if [ -f ".env" ]; then
    echo ".env already exists — keeping your existing values, only filling in what you enter next."
else
    cp .env.example .env
    echo "Created .env from .env.example."
fi
echo

echo "--- Step 6/8: Configuration ---"
echo "Enter values now, or press Enter to skip anything you don't have yet"
echo "-- you can always fill it in later by editing .env directly."
echo

# --- AudD ---
current=$(get_env_var "AUDD_API_TOKEN" ".env")
if [ -n "$current" ] && [ "$current" != "your_audd_api_token_here" ]; then
    echo "AudD API token: already set (press Enter to keep it)."
else
    echo "AudD API token: not set."
fi
read -rsp "AudD API token from https://audd.io [skip]: " input
echo
if [ -n "$input" ]; then
    set_env_var "AUDD_API_TOKEN" "$input" ".env"
    echo "Saved."
elif [ -z "$current" ] || [ "$current" == "your_audd_api_token_here" ]; then
    STILL_NEEDED+=("Get an AudD API token at https://audd.io and set AUDD_API_TOKEN in .env")
fi
echo

# --- DVinyl / MongoDB ---
current=$(get_env_var "MONGO_URI" ".env")
if [ -n "$current" ]; then
    echo "DVinyl/MongoDB URI: already set (press Enter to keep it)."
else
    echo "DVinyl/MongoDB URI: not set."
fi
read -rp "Set up DVinyl collection matching now? [y/N]: " enable_dvinyl
if [[ "$enable_dvinyl" =~ ^[Yy]$ ]]; then
    read -rsp "  MongoDB URI (mongodb://user:pass@host:27017/dvinyl?authSource=dvinyl) [skip]: " input
    echo
    if [ -n "$input" ]; then
        set_env_var "MONGO_URI" "$input" ".env"
        echo "Saved. Double check MONGO_COLLECTION_NAME/FIELD_* in .env match your instance's schema (see docs/SETUP.md)."
    else
        STILL_NEEDED+=("Set MONGO_URI in .env (DVinyl collection matching)")
    fi
elif [ -z "$current" ]; then
    echo "Skipping -- DVinyl matching stays disabled until MONGO_URI is set."
fi
echo

# --- Home Assistant ---
current=$(get_env_var "HA_URL" ".env")
if [ -n "$current" ]; then
    echo "Home Assistant: already set (press Enter to keep it)."
else
    echo "Home Assistant: not set."
fi
read -rp "Set up Home Assistant integration now? [y/N]: " enable_ha
if [[ "$enable_ha" =~ ^[Yy]$ ]]; then
    read -rp "  Home Assistant URL (e.g. http://192.168.1.50:8123) [skip]: " ha_url_input
    read -rsp "  Home Assistant Long-Lived Access Token [skip]: " ha_token_input
    echo
    if [ -n "$ha_url_input" ] && [ -n "$ha_token_input" ]; then
        set_env_var "HA_URL" "$ha_url_input" ".env"
        set_env_var "HA_TOKEN" "$ha_token_input" ".env"
        echo "Saved."
    else
        STILL_NEEDED+=("Set HA_URL and HA_TOKEN in .env (Home Assistant integration)")
    fi
elif [ -z "$current" ]; then
    echo "Skipping -- Home Assistant integration stays disabled until HA_URL/HA_TOKEN are set."
fi
echo

echo "--- Step 7/8: Samba file share ---"
sudo apt install -y samba
SMB_CONF="/etc/samba/smb.conf"
if sudo grep -q "^\[groove-tracker\]" "$SMB_CONF" 2>/dev/null; then
    echo "Samba share '[groove-tracker]' already configured — skipping share setup."
    echo "(Run 'sudo smbpasswd -a $CURRENT_USER' manually if you need to reset the Samba password.)"
else
    sudo tee -a "$SMB_CONF" > /dev/null <<EOF

[groove-tracker]
   path = $PROJECT_ROOT
   browseable = yes
   writable = yes
   read only = no
   guest ok = no
   valid users = $CURRENT_USER
EOF
    sudo systemctl restart smbd
    echo "Samba share '[groove-tracker]' added, pointing at $PROJECT_ROOT."
    echo
    echo "This needs a Samba password for $CURRENT_USER -- what you'll type when"
    echo "connecting from your computer's file browser (separate from your Pi login"
    echo "password)."
    read -rp "Set it now? [Y/n]: " set_smb_pw
    if [[ "$set_smb_pw" =~ ^[Nn]$ ]]; then
        STILL_NEEDED+=("Set a Samba password: sudo smbpasswd -a $CURRENT_USER")
    elif sudo smbpasswd -a "$CURRENT_USER"; then
        echo "Samba password set."
    else
        STILL_NEEDED+=("Set a Samba password: sudo smbpasswd -a $CURRENT_USER")
    fi
fi
echo

echo "--- Step 8/8: systemd service ---"
SERVICE_FILE="/etc/systemd/system/groove-tracker.service"
sed -e "s|__USER__|$CURRENT_USER|g" -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
    "$PROJECT_ROOT/systemd/groove-tracker.service" | sudo tee "$SERVICE_FILE" > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable groove-tracker.service
echo "Installed and enabled groove-tracker.service (will start automatically on boot)."
echo "Not starting it yet -- see the checklist below first."
echo

echo "=== Setup script complete ==="
echo

# Hardware wiring can't be detected from software, so it's always listed
# first regardless of what was configured above.
echo "Still needed:"
echo "  - Wire the display and audio tap if you haven't already (docs/SETUP.md 'Wiring')"
echo "  - Confirm DISPLAY_MODEL in .env matches your panel (epd4in2_V2 confirmed for the 4.2\" module)"
if [ "${#STILL_NEEDED[@]}" -gt 0 ]; then
    for item in "${STILL_NEEDED[@]}"; do
        echo "  - $item"
    done
else
    echo "  - (Everything else you were prompted for above is set -- nice.)"
fi
echo
echo "Then test each piece individually per docs/SETUP.md's testing section before running the full loop."
echo "Once it's working end to end, start the service: sudo systemctl start groove-tracker"
