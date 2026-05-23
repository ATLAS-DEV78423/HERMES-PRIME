#!/usr/bin/env bash
set -e

echo "=================================================="
echo "    INITIALIZING HERMES-PRIME INSTALLATION        "
echo "=================================================="

INSTALL_DIR="${HOME}/.hermes-prime"

if [ -d "$INSTALL_DIR" ]; then
    echo "[!] HERMES-PRIME is already installed at $INSTALL_DIR"
    echo "    Updating repository..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "[*] Cloning repository..."
    git clone https://github.com/ATLAS-DEV78423/HERMES-PRIME.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo "[*] Setting up deterministic Python environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "[*] Installing dependencies and core engine..."
pip install -e .

echo ""
echo "=================================================="
echo "    HERMES-PRIME INSTALLATION COMPLETE            "
echo "=================================================="
echo ""
echo "To use the CLI globally, add this alias to your ~/.bashrc or ~/.zshrc:"
echo "    alias hermes-prime='${INSTALL_DIR}/.venv/bin/hermes-prime'"
echo ""
echo "Run 'hermes-prime doctor' to verify the environment."
echo "=================================================="
