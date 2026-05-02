#!/bin/bash
# Quick deploy — copies changed source files into the installed app without rebuilding.
# Run this after editing index.html or server.py.
# Then click ↺ in the app (or restart it for server.py changes).
set -e
cd "$(dirname "$0")"

BUNDLE="$HOME/Applications/NOEMA.app"

if [ ! -d "$BUNDLE" ]; then
  echo "NOEMA.app not found in ~/Applications — run build.sh first."
  exit 1
fi

deploy_file() {
  local src="$1" name
  name="$(basename "$src")"
  for dir in "$BUNDLE/Contents/Frameworks" "$BUNDLE/Contents/Resources"; do
    [ -f "$dir/$name" ] && cp "$src" "$dir/$name" && echo "  ✓  $dir/$name"
  done
}

echo ""
echo "  ◌  Deploying to $BUNDLE..."
echo ""

for f in "$@"; do
  deploy_file "$f"
done

echo ""
echo "  ✦  Done. Click ↺ in NOEMA to reload."
echo "     (Restart the app fully if you changed server.py)"
echo ""
