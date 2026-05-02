#!/bin/bash
set -e
cd "$(dirname "$0")"

echo ""
echo "  ✦  Building NOEMA for Linux..."
echo ""

# Install system dependency for pywebview (WebKit2GTK)
if command -v apt-get &>/dev/null; then
    sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.0 2>/dev/null || true
elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3-gobject webkit2gtk4.0 2>/dev/null || true
fi

pip3 install pyinstaller pywebview --quiet --break-system-packages 2>/dev/null \
  || pip3 install pyinstaller pywebview --quiet 2>/dev/null

rm -rf build dist

pyinstaller NOEMA_linux.spec

echo ""
echo "  ✦  Done!"
echo ""
echo "  The NOEMA folder is in dist/NOEMA/"
echo ""
echo "  To distribute: tar -czf NOEMA-linux.tar.gz dist/NOEMA/"
echo "  Users run:     dist/NOEMA/NOEMA"
echo ""
echo "  Requirements for users:"
echo "    - libwebkit2gtk-4.0 (sudo apt install libwebkit2gtk-4.0-dev)"
echo "    - Ollama running at http://localhost:11434"
echo "    - For screenshots: sudo apt install scrot"
echo ""
