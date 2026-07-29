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
  "amd-without-cuda|AMD_with_cuda"
  "arm|ARM_with_cuda"
  "arm-without-cuda|ARM_without_cuda"
  "l4t"
  "thor-spark|thor_spark"
)
COMPONENTS=(
  "DESENSITIZE_FRONTEND|desensitize-frontend|swr.cn-southwest-2.myhuaweicloud.com/ictrek/desensitize-frontend"
  "DESENSITIZE_BACKEND|desensitize-backend|swr.cn-southwest-2.myhuaweicloud.com/ictrek/desensitize-backend"
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
  local body="${4:-}"
  if [[ -n "$body" ]]; then
    curl --fail -sS -X "$method" "$url" \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: application/json" \
      --data "$body"
  else
    curl --fail -sS -X "$method" "$url" \
      -H "Authorization: Bearer ${token}"
  fi
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
data = json.loads(sys.argv[1])
if data.get("code") != 0:
    sys.stderr.write(f"get_feishu_token failed: {data}\n")
    sys.exit(1)
print(data["tenant_access_token"])
PYJSON
}

get_sheet_id_by_title() {
  local token="$1"
  local target_title="$2"
  local resp
  resp="$(feishu_api_json "GET" \
    "https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/${SPREADSHEET_TOKEN}/sheets/query" \
    "$token")"
  python3 - "$target_title" "$resp" <<'PYJSON'
import json
import sys
target, resp = sys.argv[1], sys.argv[2]
data = json.loads(resp)
if data.get("code") != 0:
    raise SystemExit(f"query sheets failed: {data}")
for sheet in data.get("data", {}).get("sheets", []):
    if sheet.get("title") == target:
        print(sheet["sheet_id"])
        raise SystemExit(0)
raise SystemExit(f"sheet title not found: {target}")
PYJSON
}

get_range_values() {
  local token="$1"
  local range="$2"
  feishu_api_json "GET" \
    "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${SPREADSHEET_TOKEN}/values/${range}" \
    "$token"
}

# 列布局（与 build_image.sh 写入一致，参考 weknora/model_hub）:
#   - 第 1 行: 组件名 (desensitize_backend / desensitize_frontend)
#   - 第 2 行: 镜像仓库地址
#   - 第 4 行起: 按日期递增的 tag
# 此函数在第 1 行中查找组件列字母。
find_component_column_letter() {
  local token="$1"
  local sheet_id="$2"
  local component="$3"
  local resp
  resp="$(get_range_values "$token" "${sheet_id}!A1:ZZ1")"
  python3 - "$component" "$resp" <<'PYJSON'
import json
import sys
target, resp = sys.argv[1], sys.argv[2]
data = json.loads(resp)
if data.get("code") != 0:
    raise SystemExit(f"read header failed: {data}")
values = data.get("data", {}).get("valueRange", {}).get("values", [])
row = values[0] if values else []

def text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("link") or "").strip()
    if isinstance(value, list):
        return "".join(text(v) for v in value).strip()
    return str(value).strip()

def col(num):
    out = ""
    while num > 0:
        num, rem = divmod(num - 1, 26)
        out = chr(ord("A") + rem) + out
    return out

for index, value in enumerate(row, start=1):
    if text(value) == target:
        print(col(index))
        raise SystemExit(0)
raise SystemExit(f"component column not found in row1: {target}")
PYJSON
}

# 从指定列的第 4 行起向下读取，返回第一个非空单元格（即最新 tag）。
find_latest_tag() {
  local token="$1"
  local sheet_id="$2"
  local column="$3"
  local resp
  resp="$(get_range_values "$token" "${sheet_id}!${column}4:${column}2000")"
  python3 - "$resp" <<'PYJSON'
import json
import sys
data = json.loads(sys.argv[1])
if data.get("code") != 0:
    raise SystemExit(f"read version column failed: {data}")
values = data.get("data", {}).get("valueRange", {}).get("values", [])
for row in values:
    if not row:
        continue
    value = row[0]
    if value is None:
        continue
    text = str(value).strip()
    if text:
        print(text)
        raise SystemExit(0)
raise SystemExit("latest version not found")
PYJSON
}

# 组合查找组件列 + 读取最新 tag，返回完整镜像名。
latest_image() {
  local token="$1"
  local sheet_id="$2"
  local component="$3"
  local repository="$4"
  local column tag
  column="$(find_component_column_letter "$token" "$sheet_id" "$component")" || return 1
  tag="$(find_latest_tag "$token" "$sheet_id" "$column")" || return 1
  [[ -n "$tag" ]] || return 1
  echo "${repository}:${tag}"
}

# 将 profile 名转为 env key 后缀（与 docker-compose.yml 中的 ${VAR}_IMAGE 一致）
# 例如 amd-without-cuda -> AMD_WITHOUT_CUDA，thor-spark -> THOR_SPARK
env_key() {
  printf '%s' "$1" | tr '[:lower:]-' '[:upper:]_' | tr -c 'A-Z0-9_' '_'
}

render_template() {
  local src="$1"
  local dst="$2"
  local content
  content="$(cat "$src")"
  content="${content//__APP_VERSION__/$APP_VERSION}"
  echo "$content" > "$dst"
}

# 渲染 docker-compose.yml：先替换 __APP_VERSION__，再把 ${VAR} 形式的镜像
# 变量替换为 .env 中的值（仅对 *_IMAGE 变量做替换，保留 ${VAR:-default} 等其他语法）。
render_compose_file() {
  local src="$1"
  local dst="$2"
  local env_file="$3"
  python3 - "$src" "$dst" "$APP_VERSION" "$env_file" <<'PYRENDER'
import re
import sys
from pathlib import Path

src, dst, version, env_path = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
env = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    env[key] = value

text = src.read_text(encoding="utf-8").replace("__APP_VERSION__", version)

def replace_image_var(match):
    key = match.group(1)
    if key.endswith("_IMAGE") and key in env:
        return env[key]
    return match.group(0)

text = re.sub(r"\$\{([A-Z0-9_]+)(?::-[^}]*)?\}", replace_image_var, text)
dst.write_text(text, encoding="utf-8")
PYRENDER
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

  # 飞书 sheet 列布局（参考 weknora/model_hub）:
  #   第 1 行: 组件名; 第 2 行: 镜像仓库; 第 4 行起: 按日期的 tag
  # 同一 sheet 可被多个 profile 复用 (如 AMD_with_cuda 同时供 amd / amd-without-cuda)
  for profile_entry in "${PROFILES[@]}"; do
    local profile_name="${profile_entry%%|*}"
    local sheet_name="${profile_entry##*|}"
    # 若 profile_entry 不含 |，则 sheet 名等于 profile 名
    [[ "$sheet_name" == "$profile_entry" ]] && sheet_name="$profile_name"

    local sheet_id
    sheet_id="$(get_sheet_id_by_title "$feishu_token" "$sheet_name")" \
      || die "Failed to resolve sheet id for sheet '$sheet_name' (profile=$profile_name)"
    log "Resolved sheet: ${sheet_name} -> ${sheet_id}"

    for comp_entry in "${COMPONENTS[@]}"; do
      IFS='|' read -r env_var comp_name registry_path <<< "$comp_entry"
      local image_name
      image_name="$(latest_image "$feishu_token" "$sheet_id" "$comp_name" "$registry_path")" \
        || die "Failed to get latest image for $comp_name from sheet $sheet_name"
      local env_key="${env_var}_$(env_key "$profile_name")_IMAGE"
      echo "${env_key}=${image_name}" >> "$env_file"
      log "  ${env_key}=${image_name}"
    done
  done
}

verify_package() {
  local package_path="$1"
  local app_tarball="$2"
  local app_listing package_listing package_text manifest_text routers_text compose_text

  app_listing="$(tar tzf "$app_tarball")"
  package_listing="$(tar tf "$package_path")"
  printf '%s\n' "$app_listing" | grep -qx 'manifest.yml'
  printf '%s\n' "$app_listing" | grep -qx 'README.zh-CN.md'
  printf '%s\n' "$package_listing" | grep -qx 'app.tar.gz'
  ! printf '%s\n' "$package_listing" | grep -q '^assets/'

  package_text="$(printf '%s\n' "$app_listing" | while IFS= read -r file; do [[ "$file" == */ ]] && continue; tar xOf "$app_tarball" "$file"; printf '\n'; done)"
  if printf '%s' "$package_text" | grep -q '__[A-Z0-9_]\+__'; then
    die 'unrendered placeholder remains'
  fi

  manifest_text="$(tar xOf "$app_tarball" manifest.yml)"
  printf '%s\n' "$manifest_text" | grep -q '^[[:space:]]*frontend:[[:space:]]*$' || die 'manifest.yml frontend section missing'
  printf '%s\n' "$manifest_text" | grep -q '^[[:space:]]*enabled:[[:space:]]*true[[:space:]]*$' || die 'manifest.yml frontend.enabled must be true'
  printf '%s\n' "$manifest_text" | grep -Fq "  basePath: ${FRONTEND_BASE_PATH}" || die "manifest.yml frontend.basePath must be ${FRONTEND_BASE_PATH}"

  compose_text="$(tar xOf "$app_tarball" docker-compose.yml)"
  if printf '%s\n' "$compose_text" | grep -q '\${[^}]*_IMAGE[^}]*}'; then
    die 'unrendered image variable remains in docker-compose.yml'
  fi
  if printf '%s\n' "$compose_text" | awk '/^[[:space:]]*image:/ {print $2}' | grep -v '^[^/[:space:]]\+\.[^/[:space:]]\+/' | grep -q .; then
    die 'docker-compose.yml contains short image reference'
  fi
  printf '%s\n' "$compose_text" | grep -Fq 'HeadersRegexp(`Sec-Fetch-Dest`, `document`)' || die 'top-level document redirect missing'
  printf '%s\n' "$compose_text" | grep -Fq "${ROUTER_HASH_PATH}" || die "top-level redirect must target ${ROUTER_HASH_PATH}"
  printf '%s\n' "$compose_text" | grep -Eq '^  vos_default:$' || die 'docker-compose.yml must declare the vos_default network'
  printf '%s\n' "$compose_text" | grep -Eq '^    external: true$' || die 'vos_default must be an external VOS network'
  printf '%s\n' "$compose_text" | grep -Fq '        - desensitize-backend' || die 'backend must retain the desensitize-backend alias'
  printf '%s\n' "$compose_text" | grep -Fq '        - desensitize-frontend' || die 'frontend must retain the desensitize-frontend alias'

  routers_text="$(tar xOf "$app_tarball" routers.yml)"
  printf '%s\n' "$routers_text" | grep -Fq "  - id: ${ROUTER_GROUP_ID}" || die "routers.yml group id must be ${ROUTER_GROUP_ID}"
  printf '%s\n' "$routers_text" | grep -Fq "      - id: ${ROUTER_PAGE_ID}" || die "routers.yml page id must be ${ROUTER_PAGE_ID}"
  printf '%s\n' "$routers_text" | grep -Fq "        iframe-src: ${ROUTER_IFRAME_SRC}" || die "routers.yml iframe-src must be ${ROUTER_IFRAME_SRC}"
  if printf '%s\n' "$routers_text" | grep -Eq 'iframe-src:[[:space:]]*https?://'; then
    die 'routers.yml iframe-src must use a same-origin VOS path'
  fi
  printf '%s\n' "$routers_text" | grep -q 'entry-point:[[:space:]]*true' || die 'routers.yml entry-point missing'
  printf '%s\n' "$routers_text" | grep -q 'embed:[[:space:]]*true' || die 'routers.yml embed missing'
}

main() {
  require_cmd tar
  require_cmd python3
  require_cmd curl

  acquire_lock

  if [[ -n "${PACKAGE_VERSION:-}" ]]; then
    [[ "$PACKAGE_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid PACKAGE_VERSION: $PACKAGE_VERSION"
    APP_VERSION="$PACKAGE_VERSION"
  else
    APP_VERSION="$(read_version)"
  fi
  [[ "$APP_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid VERSION: $APP_VERSION"
  log "Building pull-mode package for ${APP_ID} version ${APP_VERSION}"

  rm -rf "$STAGE_DIR" "$PACKAGE_ROOT"
  mkdir -p "$STAGE_DIR"

  # Build .env with image names from Feishu
  log "Fetching image tags from Feishu..."
  build_env

  # Render templates (compose 文件需要先有 .env 才能替换 ${..._IMAGE} 变量)
  render_template "$SRC_DIR/manifest.yml" "$STAGE_DIR/manifest.yml"
  render_compose_file "$SRC_DIR/docker-compose.yml" "$STAGE_DIR/docker-compose.yml" "$STAGE_DIR/.env"
  render_template "$SRC_DIR/configs.yml" "$STAGE_DIR/configs.yml"
  render_template "$SRC_DIR/routers.yml" "$STAGE_DIR/routers.yml"
  render_template "$SRC_DIR/README.zh-CN.md" "$STAGE_DIR/README.zh-CN.md"
  render_template "$SRC_DIR/README.en.md" "$STAGE_DIR/README.en.md"

  local app_tarball="${DIST_DIR}/app.tar.gz"
  local tarball="${DIST_DIR}/${APP_NAME}_${APP_VERSION}_pull.tar"
  tar czf "$app_tarball" -C "$STAGE_DIR" .env manifest.yml docker-compose.yml configs.yml routers.yml README.zh-CN.md README.en.md
  rm -rf "$PACKAGE_ROOT"
  mkdir -p "$PACKAGE_ROOT"
  cp "$app_tarball" "$PACKAGE_ROOT/app.tar.gz"
  tar cf "$tarball" -C "$PACKAGE_ROOT" app.tar.gz

  verify_package "$tarball" "$app_tarball"
  log "Done: $tarball"
}

main "$@"
