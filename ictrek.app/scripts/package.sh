#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# desensitize VOS app package script
# Builds one VOS app tarball for all supported Docker Compose profiles.
#
# Usage:
#   ./scripts/package.sh
# =============================================================================

APP_NAME="desensitize"
APP_ID="com.ictrek.desensitize"
ROUTER_GROUP_ID="com-ictrek-desensitize"
ROUTER_PAGE_ID="desensitize"
ROUTER_IFRAME_SRC="/app/com.ictrek.desensitize/"
ROUTER_HASH_PATH="#/app/com.ictrek.desensitize/com-ictrek-desensitize/desensitize"
FRONTEND_BASE_PATH="/app/com.ictrek.desensitize"
SPREADSHEET_TOKEN="${FEISHU_SPREADSHEET_TOKEN:-Htotsn3oahO1zxt73YMcaB1zn8e}"
FEISHU_CONFIG_FILE="${FEISHU_CONFIG_FILE:-${HOME}/.feishu.components.json}"
FEISHU_FALLBACK_CONFIG_FILE="${FEISHU_FALLBACK_CONFIG_FILE:-${HOME}/.feishu.json}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/src"
DIST_DIR="${ROOT_DIR}/dist"
STAGE_DIR="${DIST_DIR}/staging"
PACKAGE_ROOT="${DIST_DIR}/package-root"
VERSION_FILE="${ROOT_DIR}/VERSION"
LOCK_DIR="${DIST_DIR}/.package.lock"

PROFILES=(
  "amd|AMD_with_cuda"
  "arm|ARM_with_cuda"
)
COMPONENTS=(
  "DESENSITIZE_FRONTEND|desensitize_frontend|swr.cn-southwest-2.myhuaweicloud.com/ictrek/desensitize-frontend"
  "DESENSITIZE_BACKEND|desensitize_backend|swr.cn-southwest-2.myhuaweicloud.com/ictrek/desensitize-backend"
)

log() { echo "[INFO] $*"; }
err() { echo "[ERROR] $*" >&2; }
die() { err "$*"; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

acquire_lock() {
  mkdir -p "$(dirname "$LOCK_DIR")"
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    sleep 1
  done
  trap 'rm -rf "$LOCK_DIR"' EXIT
}

read_version() {
  [[ -f "$VERSION_FILE" ]] || echo "0.0.0" > "$VERSION_FILE"
  tr -d '[:space:]' < "$VERSION_FILE"
}

read_feishu_field() {
  local config_file="$1"
  local field="$2"
  python3 - "$config_file" "$field" <<'PYJSON'
import json
import sys
path, field = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
val = data.get(field, "")
print(val if isinstance(val, str) else str(val))
PYJSON
}

feishu_api_json() {
  local method="$1"
  local url="$2"
  local token="$3"
  curl --fail -sS -X "$method" "$url" -H "Authorization: Bearer ${token}"
}

get_feishu_token() {
  local app_id="$1"
  local app_secret="$2"
  local resp
  resp="$(
    curl --fail -sS -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
      -H "Content-Type: application/json" \
      -d "{\"app_id\":\"${app_id}\",\"app_secret\":\"${app_secret}\"}"
  )"
  python3 - "$resp" <<'PYJSON'
import json
import sys
data = json.load(sys.stdin)
token = data.get("tenant_access_token", "")
if not token:
    sys.stderr.write(f"Failed to get Feishu token: {data}\n")
    sys.exit(1)
print(token)
PYJSON
}

get_latest_tag() {
  local token="$1"
  local sheet_name="$2"
  local component_name="$3"

  local url="https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${SPREADSHEET_TOKEN}/values/${sheet_name}!A:Z"
  local resp
  resp="$(feishu_api_json GET "$url" "$token")"

  python3 - "$resp" "$component_name" <<'PYJSON'
import json
import sys

resp = json.loads(sys.argv[1])
component_name = sys.argv[2]

rows = resp.get("data", {}).get("valueRange", {}).get("values", [])
if not rows:
    sys.stderr.write(f"No data in sheet\n")
    sys.exit(1)

# Find component and tag columns
header = rows[0]
component_col = None
tag_col = None
for i, cell in enumerate(header):
    cell_text = str(cell).strip().lower() if cell else ""
    if "component" in cell_text or "组件" in cell_text:
        component_col = i
    if "tag" in cell_text or "标签" in cell_text or "版本" in cell_text:
        tag_col = i

if component_col is None or tag_col is None:
    sys.stderr.write(f"Cannot find component/tag columns in sheet\n")
    sys.exit(1)

for row in rows[1:]:
    if len(row) > component_col and str(row[component_col]).strip() == component_name:
        if len(row) > tag_col and row[tag_col]:
            print(str(row[tag_col]).strip())
            sys.exit(0)

sys.stderr.write(f"Component {component_name} not found in sheet\n")
sys.exit(1)
PYJSON
}

render_template() {
  local src="$1"
  local dst="$2"
  local content
  content="$(cat "$src")"
  content="${content//__APP_VERSION__/$APP_VERSION}"
  echo "$content" > "$dst"
}

build_env() {
  local env_file="$STAGE_DIR/.env"
  : > "$env_file"

  local feishu_app_id feishu_app_secret feishu_token
  if [[ -f "$FEISHU_CONFIG_FILE" ]]; then
    feishu_app_id="$(read_feishu_field "$FEISHU_CONFIG_FILE" "feishu_app_id")"
    feishu_app_secret="$(read_feishu_field "$FEISHU_CONFIG_FILE" "feishu_app_secret")"
  elif [[ -f "$FEISHU_FALLBACK_CONFIG_FILE" ]]; then
    feishu_app_id="$(read_feishu_field "$FEISHU_FALLBACK_CONFIG_FILE" "feishu_app_id")"
    feishu_app_secret="$(read_feishu_field "$FEISHU_FALLBACK_CONFIG_FILE" "feishu_app_secret")"
  fi

  if [[ -n "$feishu_app_id" && -n "$feishu_app_secret" ]]; then
    feishu_token="$(get_feishu_token "$feishu_app_id" "$feishu_app_secret")"
  else
    die "Feishu credentials not found in $FEISHU_CONFIG_FILE or $FEISHU_FALLBACK_CONFIG_FILE"
  fi

  for profile_entry in "${PROFILES[@]}"; do
    local profile_name="${profile_entry%%|*}"
    local sheet_name="${profile_entry##*|}"

    for comp_entry in "${COMPONENTS[@]}"; do
      IFS='|' read -r env_var comp_name registry_path <<< "$comp_entry"
      local image_tag
      image_tag="$(get_latest_tag "$feishu_token" "$sheet_name" "$comp_name")" || die "Failed to get tag for $comp_name from sheet $sheet_name"
      local image_name="${registry_path}:${image_tag}"
      local env_key="${env_var}_${profile_name^^}_IMAGE"
      echo "${env_key}=${image_name}" >> "$env_file"
      log "  ${env_key}=${image_name}"
    done
  done
}

verify_package() {
  local tarball="$1"
  log "Verifying package: $tarball"

  local tmpdir
  tmpdir="$(mktemp -d)"
  tar xzf "$tarball" -C "$tmpdir"

  # Check manifest exists
  [[ -f "$tmpdir/manifest.yml" ]] || die "manifest.yml not found in package"

  # Check no template placeholders remain
  if grep -r '__[A-Z_]*__' "$tmpdir/" 2>/dev/null; then
    die "Unresolved template placeholders found in package"
  fi

  # Check docker-compose has no unresolved image variables
  if grep -E '\$\{[A-Z_]+_IMAGE\}' "$tmpdir/docker-compose.yml" 2>/dev/null; then
    die "Unresolved image variables in docker-compose.yml"
  fi

  # Check frontend fields exist
  grep -q 'frontend:' "$tmpdir/manifest.yml" || die "frontend section missing in manifest.yml"
  grep -q 'enabled: true' "$tmpdir/manifest.yml" || die "frontend.enabled not true in manifest.yml"

  # Check Sec-Fetch-Dest redirect exists
  grep -q 'Sec-Fetch-Dest' "$tmpdir/docker-compose.yml" || die "Sec-Fetch-Dest redirect missing in docker-compose.yml"

  # Check routers.yml has entry-point and embed
  grep -q 'entry-point: true' "$tmpdir/routers.yml" || die "entry-point: true missing in routers.yml"
  grep -q 'embed: true' "$tmpdir/routers.yml" || die "embed: true missing in routers.yml"

  rm -rf "$tmpdir"
  log "Package verification passed"
}

main() {
  require_cmd tar
  require_cmd python3
  require_cmd curl

  acquire_lock

  APP_VERSION="$(read_version)"
  log "Building package for ${APP_ID} version ${APP_VERSION}"

  rm -rf "$STAGE_DIR" "$PACKAGE_ROOT"
  mkdir -p "$STAGE_DIR"

  # Render templates
  render_template "$SRC_DIR/manifest.yml" "$STAGE_DIR/manifest.yml"
  cp "$SRC_DIR/docker-compose.yml" "$STAGE_DIR/docker-compose.yml"
  cp "$SRC_DIR/configs.yml" "$STAGE_DIR/configs.yml"
  cp "$SRC_DIR/routers.yml" "$STAGE_DIR/routers.yml"
  cp "$SRC_DIR/README.zh-CN.md" "$STAGE_DIR/README.zh-CN.md"
  cp "$SRC_DIR/README.en.md" "$STAGE_DIR/README.en.md"

  # Build .env with image names from Feishu
  log "Fetching image tags from Feishu..."
  build_env

  # Create app.tar.gz
  local tarball="${DIST_DIR}/${APP_NAME}_${APP_VERSION}_pull.tar"
  tar czf "$tarball" -C "$STAGE_DIR" .
  log "Created package: $tarball"

  verify_package "$tarball"

  log "Done: $tarball"
}

main "$@"
