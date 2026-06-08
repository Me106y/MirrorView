#!/bin/bash
# MirrorView-TTS — One-Click Startup
# ===================================
# Uses Python 3.14 (Homebrew) + DeepSeek + Boson TTS
#
# Usage:
#   chmod +x start.sh
#   ./start.sh

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# ── Python 3.14 (Homebrew) ──
PYTHON=/opt/homebrew/bin/python3.14

# ── API Keys ──
# Create .env_tts with your real keys (this file is gitignored):
#   export DEEPSEEK_API_KEY="sk-xxx"
#   export BOSON_API_KEY="bai-xxx"
[ -f "$DIR/.env_tts" ] && source "$DIR/.env_tts"
export MIRRORVIEW_DB_PATH="${MIRRORVIEW_DB_PATH:-/tmp/mirrorview.db}"
export PYTHONPATH="$DIR"

echo "╔══════════════════════════════════════════════╗"
echo "║   🎙️  MirrorView-TTS — AI Mock Interview   ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  Python: $($PYTHON --version)"
echo "  LLM:    DeepSeek-V3 (deepseek-chat)"
echo "  TTS:    Boson.ai Higgs Audio v3"
echo "  Embed:  HuggingFace (local, free)"
echo ""

# Kill existing
lsof -ti :5001 | xargs kill -9 2>/dev/null || true
sleep 1

# Clear Python cache
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Start server
echo "[1/2] Starting server on http://localhost:5001 ..."
$PYTHON server/app.py > /tmp/mirrorview_server.log 2>&1 &
SERVER_PID=$!

for i in 1 2 3 4 5 6 7 8; do
    sleep 1
    if curl -s http://localhost:5001/api/tts/health > /dev/null 2>&1; then
        echo "       ✅ Server ready"
        break
    fi
    if [ $i -eq 8 ]; then
        echo "       ❌ Server failed"
        tail -5 /tmp/mirrorview_server.log
        exit 1
    fi
done

# Start client
echo "[2/2] Launching desktop client..."
echo ""
echo "   📱 Login window should appear."
echo "   👤 Register any username/password"
echo "   🎯 Start New Interview → Choose Voice Mode"
echo ""
echo "   💬 Classic Mode: text chat + camera + AI"
echo "   🎙️ Voice Mode:  camera + AI avatar + TTS voice"
echo ""
echo "   🤖 LLM:  DeepSeek-V3  (cheap, fast)"
echo "   🔊 TTS:  Higgs Audio  (real-time voice)"
echo ""

$PYTHON client/main.py > /tmp/mirrorview_client.log 2>&1 &
CLIENT_PID=$!

echo "Server PID: $SERVER_PID  |  Client PID: $CLIENT_PID"
echo "Press Ctrl+C to stop."

trap "kill $SERVER_PID $CLIENT_PID 2>/dev/null; echo 'Stopped.'" EXIT
wait $CLIENT_PID 2>/dev/null
