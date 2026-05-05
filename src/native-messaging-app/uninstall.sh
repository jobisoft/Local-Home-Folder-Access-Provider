#!/usr/bin/env bash
# Uninstall the expose_home_folder_host native messaging host for Thunderbird on Linux/macOS.

set -euo pipefail

if [[ "$OSTYPE" == darwin* ]]; then
  HOSTS_DIR="$HOME/Library/Application Support/Mozilla/NativeMessagingHosts"
else
  HOSTS_DIR="$HOME/.mozilla/native-messaging-hosts"
fi

INSTALL_DIR="$HOSTS_DIR/expose_home_folder_host_helper"
MANIFEST_DEST="$HOSTS_DIR/expose_home_folder_host.json"

echo
echo "This will uninstall the file system access helper app for the Thunderbird"
echo "add-on \"VFS-Provider: Local Home Folder Access\"."
echo
echo "The following will happen:"
echo "  - Remove the manifest:"
echo "      $MANIFEST_DEST"
echo "  - Remove the file system access helper app from:"
echo "      $INSTALL_DIR"
echo

read -p "Proceed with uninstallation? [y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Uninstallation cancelled."
  echo
  read -n1 -s -r -p "Press any key to exit..."
  echo
  exit 1
fi
echo

if [[ -f "$MANIFEST_DEST" ]]; then
  rm "$MANIFEST_DEST"
  echo "Removed: $MANIFEST_DEST"
else
  echo "Not installed (not found): $MANIFEST_DEST"
fi

if [[ -d "$INSTALL_DIR" ]]; then
  rm -rf "$INSTALL_DIR"
  echo "Removed install dir: $INSTALL_DIR"
else
  echo "Not installed (not found): $INSTALL_DIR"
fi

echo
read -n1 -s -r -p "Press any key to exit..."
echo
