#!/bin/bash
# Groove Tracker setup script — the one command that installs everything.
#
# Automates: system packages (including everything discovered the hard way
# while building this — see docs/SETUP.md's troubleshooting appendix),
# enabling SPI, cloning the Waveshare e-Paper driver into the right place,
# creating the venv and installing Python dependencies, setting up a Samba
# file share, and installing (but not starting) the systemd service.
# Safe to re-run — skips steps that are already done rather than redoing
# them or overwriting your .env.
#
# What this CANNOT do for you (needs a human — see the checklist this
# script prints at the end, and docs/SETUP.md for details):
#   - Physically wiring the display and audio tap
#   - Signing up for an AudD API token
#   - Creating the read-only MongoDB user on your DVinyl instance
#   - Creating a Home Assistant Long-Lived Access Token
#   - Filling in the real values in .env
#   - Setting a Samba password (can't safely automate a password prompt)
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

echo "--- Step 1/7: System packages ---"
sudo apt update
sudo apt install -y python3-pip python3-venv git \
    libopenjp2-7 libopenblas-dev portaudio19-dev libsndfile1 libfreetype6
echo

echo "--- Step 2/7: Enabling SPI ---"
if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_spi 0
    echo "SPI enabled."
else
    echo "raspi-config not found — skipping (enable SPI manually if this isn't a Raspberry Pi)."
fi
echo

echo "--- Step 3/7: Waveshare e-Paper driver ---"
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

echo "--- Step 4/7: Python virtual environment ---"
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

echo "--- Step 5/7: Environment file ---"
if [ -f ".env" ]; then
    echo ".env already exists — leaving it alone."
    echo "If requirements have changed, compare against .env.example for any new variables to add."
else
    cp .env.example .env
    echo "Created .env from .env.example — you MUST edit this before running the project."
fi
echo

echo "--- Step 6/7: Samba file share ---"
sudo apt install -y samba
SMB_CONF="/etc/samba/smb.conf"
if sudo grep -q "^\[groove-tracker\]" "$SMB_CONF" 2>/dev/null; then
    echo "Samba share '[groove-tracker]' already configured — skipping."
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
    echo "You still need to set a Samba password (separate from your login password) -- see the checklist below."
fi
echo

echo "--- Step 7/7: systemd service ---"
SERVICE_FILE="/etc/systemd/system/groove-tracker.service"
sed -e "s|__USER__|$CURRENT_USER|g" -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
    "$PROJECT_ROOT/systemd/groove-tracker.service" | sudo tee "$SERVICE_FILE" > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable groove-tracker.service
echo "Installed and enabled groove-tracker.service (will start automatically on boot)."
echo "Not starting it yet -- .env still needs real values first (see checklist below)."
echo

echo "=== Setup script complete ==="
echo
echo "Still needed before this will actually run (all manual, see docs/SETUP.md for details):"
echo "  1. Wire the display and audio tap if you haven't already (docs/SETUP.md 'Wiring')"
echo "  2. Confirm DISPLAY_MODEL in .env matches your panel (epd4in2_V2 confirmed for the 4.2\" module)"
echo "  3. Get an AudD API token at https://audd.io and set AUDD_API_TOKEN in .env"
echo "  4. Create a read-only MongoDB user on your DVinyl instance and set MONGO_URI in .env"
echo "  5. (Optional) Create a Home Assistant Long-Lived Access Token and set HA_URL/HA_TOKEN in .env"
echo "  6. Set a Samba password: sudo smbpasswd -a $CURRENT_USER"
echo "  7. Edit .env: nano $PROJECT_ROOT/.env"
echo
echo "Then test each piece individually per docs/SETUP.md's testing section before running the full loop."
echo "Once it's working end to end, start the service: sudo systemctl start groove-tracker"
