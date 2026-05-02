#!/bin/bash
cd "$(dirname "$0")"

echo ""
echo "  ✦  NOEMA — starting up..."
echo ""

# Keep Mac awake (lid closed = fine as long as power is connected)
caffeinate -i -w $$ &

# Install Python deps silently
echo "  ◌  Checking dependencies..."
pip3 install fastapi uvicorn requests beautifulsoup4 --quiet --break-system-packages 2>/dev/null \
  || pip3 install fastapi uvicorn requests beautifulsoup4 --quiet 2>/dev/null

# Kill anything already on port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Start the server
echo "  ◌  Starting server..."
python3 server.py &
SERVER_PID=$!

# Wait for it to come up
sleep 3

# Open browser
open http://localhost:8000

# Try ngrok if installed
if command -v ngrok &>/dev/null; then
  echo ""
  echo "  ◌  Starting ngrok tunnel..."
  ngrok http 8000 --log=stdout > /tmp/noema_ngrok.log 2>&1 &
  NGROK_PID=$!
  sleep 4
  NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])" 2>/dev/null)
  if [ -n "$NGROK_URL" ]; then
    echo ""
    echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  📱 PHONE URL:  $NGROK_URL"
    echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  (Password shown above — enter it on your phone)"
    echo ""
  fi
else
  echo ""
  echo "  ⚠  ngrok not found. To access from your phone:"
  echo "     1. Go to https://ngrok.com and make a free account"
  echo "     2. Run:  brew install ngrok"
  echo "     3. Run:  ngrok config add-authtoken YOUR_TOKEN"
  echo "     4. Restart NOEMA"
  echo ""
fi

echo "  ✦  NOEMA is running. Close this window to stop everything."
echo ""

# Wait for server — closing this window kills everything
wait $SERVER_PID
