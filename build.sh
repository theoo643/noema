#!/bin/bash
set -e
cd "$(dirname "$0")"

echo ""
echo "  ✦  Building NOEMA.app..."
echo ""

pip3 install pyinstaller pywebview --quiet --break-system-packages 2>/dev/null \
  || pip3 install pyinstaller pywebview --quiet 2>/dev/null

rm -rf build dist

pyinstaller NOEMA.spec

echo ""
echo "  ◌  Packaging NOEMA.app..."
rm -rf NOEMA.app
cp -r dist/NOEMA.app .

# Inject custom icon
if [ -f noema.icns ]; then
  cp noema.icns NOEMA.app/Contents/Resources/icon-windowed.icns
fi

# Strip extended attributes and sign
xattr -rc NOEMA.app 2>/dev/null || true
codesign -s - --force NOEMA.app/Contents/MacOS/NOEMA 2>/dev/null || true
xattr -d com.apple.quarantine NOEMA.app 2>/dev/null || true

echo "  ◌  Installing to ~/Applications..."
rm -rf "$HOME/Applications/NOEMA.app"
cp -r NOEMA.app "$HOME/Applications/NOEMA.app"
xattr -rc "$HOME/Applications/NOEMA.app" 2>/dev/null || true
xattr -d com.apple.quarantine "$HOME/Applications/NOEMA.app" 2>/dev/null || true

echo ""
echo "  ◌  Creating NOEMA.dmg..."

DMG_TMP="dist/dmg_tmp"
rm -rf "$DMG_TMP"
mkdir -p "$DMG_TMP"
cp -r NOEMA.app "$DMG_TMP/"
ln -s /Applications "$DMG_TMP/Applications"

hdiutil create \
    -volname "NOEMA" \
    -srcfolder "$DMG_TMP" \
    -ov -format UDZO \
    "NOEMA.dmg" >/dev/null

rm -rf "$DMG_TMP"
xattr -d com.apple.quarantine NOEMA.dmg 2>/dev/null || true

echo ""
echo "  ✦  Done!"
echo ""
echo "  NOEMA.app        — installed to ~/Applications"
echo "  NOEMA.dmg        — share this to distribute NOEMA"
echo ""
echo "  To install from DMG: open NOEMA.dmg, drag NOEMA → Applications"
echo "  If macOS blocks it:   right-click → Open → Open"
echo ""
