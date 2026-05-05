#!/usr/bin/env bash
# Install the expose_home_folder_host native messaging host for Thunderbird on Linux/macOS.
# Copies runtime files into the user-level Mozilla native-messaging-hosts dir so the
# source folder can be deleted afterwards.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SRC="$SCRIPT_DIR/expose_home_folder_host.py"
MANIFEST_SRC="$SCRIPT_DIR/expose_home_folder_host.json"

if [[ "$OSTYPE" == darwin* ]]; then
  HOSTS_DIR="$HOME/Library/Application Support/Mozilla/NativeMessagingHosts"
else
  HOSTS_DIR="$HOME/.mozilla/native-messaging-hosts"
fi

INSTALL_DIR="$HOSTS_DIR/expose_home_folder_host_helper"
PY_DEST="$INSTALL_DIR/expose_home_folder_host.py"
MANIFEST_DEST="$HOSTS_DIR/expose_home_folder_host.json"

PYTHON_PRESENT=0
if command -v python3 >/dev/null 2>&1 && python3 -c "import sys; sys.exit(0)" >/dev/null 2>&1; then
  PYTHON_PRESENT=1
fi

echo
echo "This will install the file system access helper app for the Thunderbird"
echo "add-on \"VFS-Provider: Local Home Folder Access\"."
echo
echo "The following will happen:"
if [[ $PYTHON_PRESENT -eq 1 ]]; then
  echo "  - Python 3: already installed, no action needed"
else
  echo "  - Python 3: not detected (please install via your system's package manager)"
fi
echo "  - Copy the file system access helper app into:"
echo "      $INSTALL_DIR"
echo "  - Install the manifest at:"
echo "      $MANIFEST_DEST"
echo

read -p "Proceed with installation? [y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Installation cancelled."
  echo
  read -n1 -s -r -p "Press any key to exit..."
  echo
  exit 1
fi
echo

if [[ $PYTHON_PRESENT -eq 0 ]]; then
  echo "Please ensure a working Python environment, otherwise the file system
  echo "access helper app will not work."
  echo
fi

mkdir -p "$INSTALL_DIR"
cp "$PY_SRC" "$PY_DEST"
chmod +x "$PY_DEST"

sed "s|/path/to/native-messaging-app/expose_home_folder_host.py|$PY_DEST|" "$MANIFEST_SRC" > "$MANIFEST_DEST"

echo "Installed to:  $INSTALL_DIR"
echo "Manifest at:   $MANIFEST_DEST"
echo
echo "Restart Thunderbird to apply the changes."
echo "The downloaded files can now be safely removed."
echo
read -n1 -s -r -p "Press any key to exit..."
echo
