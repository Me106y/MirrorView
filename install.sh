#!/usr/bin/env bash
set -euo pipefail

REPO="${MIRRORVIEW_GITHUB_REPO:-Zhuanz/MirrorView}"
REQUESTED_VERSION="${1:-latest}"
INSTALL_BASE="${MIRRORVIEW_INSTALL_BASE:-$HOME/.mirrorview-tui}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ "$(uname -s)" == "Darwin" ]]; then
  PLATFORM="macos"
elif [[ "$(uname -s)" == "Linux" ]]; then
  PLATFORM="linux"
else
  echo "[MirrorView TUI] Unsupported platform: $(uname -s)"
  exit 1
fi

MACHINE="$(uname -m)"
if [[ "$MACHINE" == "x86_64" || "$MACHINE" == "amd64" ]]; then
  ARCH="x64"
elif [[ "$MACHINE" == "arm64" || "$MACHINE" == "aarch64" ]]; then
  ARCH="arm64"
else
  echo "[MirrorView TUI] Unsupported architecture: $MACHINE"
  exit 1
fi

if [[ "$REQUESTED_VERSION" == "latest" ]]; then
  RELEASE_API="https://api.github.com/repos/${REPO}/releases/latest"
else
  TAG="$REQUESTED_VERSION"
  if [[ "$TAG" != tui-v* ]]; then
    TAG="tui-v${TAG}"
  fi
  RELEASE_API="https://api.github.com/repos/${REPO}/releases/tags/${TAG}"
fi

echo "[MirrorView TUI] Resolving release (${REQUESTED_VERSION}) for ${PLATFORM}-${ARCH} ..."
META_FILE="$TMP_DIR/release.json"
curl -fsSL "$RELEASE_API" -o "$META_FILE"

mapfile -t META < <(python - "$META_FILE" "$PLATFORM" "$ARCH" <<'PY'
import json
import re
import sys
from pathlib import Path

meta_path, platform_tag, arch_tag = sys.argv[1:4]
data = json.loads(Path(meta_path).read_text(encoding="utf-8"))
tag = data.get("tag_name") or ""
assets = data.get("assets") or []
pattern = re.compile(rf"mirrorview-tui-.*-{platform_tag}-{arch_tag}\.(?:tar\.gz|zip)$")

for item in assets:
    name = item.get("name") or ""
    if pattern.fullmatch(name):
        print(tag)
        print(name)
        print(item.get("browser_download_url") or "")
        sys.exit(0)

sys.exit(2)
PY
)

if [[ "${#META[@]}" -lt 3 ]]; then
  echo "[MirrorView TUI] No prebuilt asset found for ${PLATFORM}-${ARCH} in release."
  exit 1
fi

TAG_NAME="${META[0]}"
ASSET_NAME="${META[1]}"
ASSET_URL="${META[2]}"

if [[ -z "$TAG_NAME" || -z "$ASSET_NAME" || -z "$ASSET_URL" ]]; then
  echo "[MirrorView TUI] Invalid release metadata."
  exit 1
fi

TARGET_DIR="${INSTALL_BASE}/${TAG_NAME}"
mkdir -p "$INSTALL_BASE"
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"

ASSET_FILE="$TMP_DIR/$ASSET_NAME"
echo "[MirrorView TUI] Downloading $ASSET_NAME ..."
curl -fL "$ASSET_URL" -o "$ASSET_FILE"

echo "[MirrorView TUI] Installing into $TARGET_DIR ..."
if [[ "$ASSET_NAME" == *.zip ]]; then
  unzip -q "$ASSET_FILE" -d "$TARGET_DIR"
else
  tar -xzf "$ASSET_FILE" -C "$TARGET_DIR"
fi

ENV_FILE="${INSTALL_BASE}/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<'EOF'
# MirrorView TUI runtime config
DEEPSEEK_API_KEY=sk-xxxx
EOF
fi

mkdir -p "$HOME/.local/bin"
BIN_LINK="$HOME/.local/bin/mirrorview-tui"

if [[ "$PLATFORM" == "macos" ]]; then
  APP_SRC="$TARGET_DIR/MirrorView TUI.app"
  if [[ ! -d "$APP_SRC" ]]; then
    echo "[MirrorView TUI] Missing app bundle: $APP_SRC"
    exit 1
  fi
  mkdir -p "$HOME/Applications"
  ln -sfn "$APP_SRC" "$HOME/Applications/MirrorView TUI.app"
  cat > "$BIN_LINK" <<'EOF'
#!/usr/bin/env bash
open "$HOME/Applications/MirrorView TUI.app"
EOF
  chmod +x "$BIN_LINK"
  echo "[MirrorView TUI] App installed: $HOME/Applications/MirrorView TUI.app"
else
  APP_BIN="$TARGET_DIR/mirrorview-tui"
  if [[ ! -f "$APP_BIN" ]]; then
    echo "[MirrorView TUI] Missing binary: $APP_BIN"
    exit 1
  fi
  chmod +x "$APP_BIN"
  ln -sfn "$APP_BIN" "$BIN_LINK"

  DESKTOP_DIR="$HOME/.local/share/applications"
  mkdir -p "$DESKTOP_DIR"
  DESKTOP_FILE="$DESKTOP_DIR/mirrorview-tui.desktop"
  if [[ -f "$TARGET_DIR/MirrorView TUI.desktop" ]]; then
    sed "s|__MIRRORVIEW_EXEC__|$APP_BIN|g" "$TARGET_DIR/MirrorView TUI.desktop" > "$DESKTOP_FILE"
  else
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=MirrorView TUI
Comment=MirrorView CareerForge terminal UI
Exec=$APP_BIN
Terminal=true
Categories=Utility;Development;
EOF
  fi
  chmod +x "$DESKTOP_FILE"

  if [[ -d "$HOME/Desktop" ]]; then
    cp "$DESKTOP_FILE" "$HOME/Desktop/MirrorView TUI.desktop" || true
    chmod +x "$HOME/Desktop/MirrorView TUI.desktop" || true
  fi

  echo "[MirrorView TUI] Desktop launcher installed: $DESKTOP_FILE"
fi

echo ""
echo "[MirrorView TUI] Installation complete."
echo "1) Set your key in: $ENV_FILE"
echo "2) Start app:"
if [[ "$PLATFORM" == "macos" ]]; then
  echo "   - Click: ~/Applications/MirrorView TUI.app"
else
  echo "   - CLI: mirrorview-tui"
  echo "   - Or click desktop launcher (if supported by your desktop environment)"
fi
echo ""
echo "Tip: if 'mirrorview-tui' is not found, add ~/.local/bin to PATH."
