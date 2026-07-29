#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# desensitize build/push script
# =============================================================================
# 在构建机本地执行：构建 docker 镜像、推送到 SWR、将 tag 写入飞书发布表。
#
# 使用方式（在构建机上执行）：
#   tc232:  ./docker/build_image.sh              # 构建 amd，写入 AMD_with_cuda
#   tc192:  ./docker/build_image.sh --sheet l4t  # 构建 arm，写入 l4t
#   tc81:   ./docker/build_image.sh              # 构建 arm，写入所有 ARM sheets
#
# 架构与 sheet 对应关系（参考 model_hub）：
#   x86_64  -> amd 镜像 -> 默认写入 AMD_with_cuda
#   aarch64 -> arm 镜像 -> 默认写入 ARM_with_cuda, ARM_without_cuda, l4t, thor_spark
#
# 说明：当前纯正则阶段，arm / l4t / thor-spark 共用同一个 arm 镜像（Dockerfile 相同），
#       差别仅在于 docker-compose profile 是否声明 runtime: nvidia。
# =============================================================================

cd "$(dirname "$0")/.."

FEISHU_CONFIG_FILE="${FEISHU_CONFIG_FILE:-${HOME}/.feishu.json}"
FEISHU_SPREADSHEET_TOKEN="${FEISHU_SPREADSHEET_TOKEN:-Htotsn3oahO1zxt73YMcaB1zn8e}"
REGISTRY="${REGISTRY:-swr.cn-southwest-2.myhuaweicloud.com/ictrek}"

BACKEND_REPOSITORY="${REGISTRY}/desensitize-backend"
FRONTEND_REPOSITORY="${REGISTRY}/desensitize-frontend"
BACKEND_COMPONENT_NAME="desensitize_backend"
FRONTEND_COMPONENT_NAME="desensitize_frontend"

AMD_SHEETS=("AMD_with_cuda")
ARM_SHEETS=("ARM_with_cuda" "ARM_without_cuda" "l4t" "thor_spark")

TODAY="$(date +%Y%m%d)"
TAG_OVERRIDE=""

BUILD_BACKEND=1
BUILD_FRONTEND=1
PUSH_IMAGES=1
UPDATE_FEISHU=1
DRY_RUN=0
SKIP_BUILD=0

TARGET=""
TARGET_SHEETS=()

log() { echo "[INFO] $*"; }
err() { echo "[ERROR] $*" >&2; }
die() { err "$*"; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

usage() {
  cat <<'EOF'
Usage: ./docker/build_image.sh [options]

Build desensitize images locally and record tags in Feishu.

Options:
  --component backend      Build only backend image
  --component frontend     Build only frontend image
  --no-push                Build locally without docker push
  --no-feishu              Do not update Feishu after push
  --feishu-only            Do not build or push; only write tags to Feishu
  --dry-run                Print plan without building, pushing, or writing Feishu
  --target TARGET          Override detected target: amd or arm
  --sheet SHEET            Override Feishu sheets to write (can be repeated)
  --tag TAG                Override the generated tag (default: <arch>_<YYYYMMDD>)
  -h, --help               Show this help

Environment:
  FEISHU_CONFIG_FILE       Defaults to ~/.feishu.json
  REGISTRY                 SWR registry prefix
EOF
}

# =============================================================================
# Feishu helpers (ported from weknora/build_image.sh)
# =============================================================================

read_feishu_field() {
  local field="$1"
  python3 - "$FEISHU_CONFIG_FILE" "$field" <<'PY'
import json, sys
path, field = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
val = data.get(field, "")
if not isinstance(val, str):
    val = str(val)
print(val)
PY
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

  resp=$(
    curl --fail -sS -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
      -H "Content-Type: application/json" \
      -d "{\"app_id\":\"${app_id}\",\"app_secret\":\"${app_secret}\"}"
  ) || die "get_feishu_token: curl failed"

  python3 - "$resp" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
if data.get("code") != 0:
    raise SystemExit(f"get_feishu_token failed: {data}")
print(data["tenant_access_token"])
PY
}

get_sheet_id_by_title() {
  local token="$1"
  local target_title="$2"
  local resp

  resp=$(
    feishu_api_json "GET" \
      "https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/sheets/query" \
      "$token"
  )

  python3 - "$target_title" "$resp" <<'PY'
import json, sys
target, resp = sys.argv[1], sys.argv[2]
data = json.loads(resp)
if data.get("code") != 0:
    raise SystemExit(f"query sheets failed: {data}")
for sheet in data.get("data", {}).get("sheets", []):
    if sheet.get("title") == target:
        print(sheet["sheet_id"])
        raise SystemExit(0)
raise SystemExit(f"sheet title not found: {target}")
PY
}

get_range_values() {
  local token="$1"
  local range="$2"

  feishu_api_json "GET" \
    "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/values/${range}" \
    "$token"
}

write_cell() {
  local token="$1"
  local sheet_id="$2"
  local cell="$3"
  local value="$4"
  local resp

  resp=$(
    feishu_api_json "PUT" \
      "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/values" \
      "$token" \
      "{\"valueRange\":{\"range\":\"${sheet_id}!${cell}:${cell}\",\"values\":[[\"${value}\"]]}}"
  )

  python3 - "$resp" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
if data.get("code") != 0:
    raise SystemExit(f"write_cell failed: {data}")
PY
}

column_letter() {
  python3 - "$1" <<'PY'
import sys
n = int(sys.argv[1])
s = ""
while n > 0:
    n, r = divmod(n - 1, 26)
    s = chr(ord("A") + r) + s
print(s)
PY
}

find_or_create_component_column() {
  local token="$1"
  local sheet_id="$2"
  local component_name="$3"
  local resp_file result status value meta_resp column_count resp2 cell

  resp_file="$(mktemp)"
  get_range_values "$token" "${sheet_id}!A1:ZZ2" > "$resp_file"

  result=$(python3 - "$component_name" "$resp_file" <<'PY'
import json, sys
target = sys.argv[1]
with open(sys.argv[2], "r", encoding="utf-8") as f:
    data = json.load(f)
if data.get("code") != 0:
    raise SystemExit(f"read header failed: {data}")
values = data.get("data", {}).get("valueRange", {}).get("values", [])
row = values[0] if values else []
repo_row = values[1] if len(values) > 1 else []

def cell_text(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return str(v.get("text") or v.get("link") or "").strip()
    if isinstance(v, list):
        return "".join(cell_text(x) for x in v).strip()
    return str(v).strip()

max_len = max(len(row), len(repo_row))

# 先在已有头部范围内查找
for i in range(2, max_len + 1):
    header = cell_text(row[i - 1]) if i <= len(row) else ""
    repo = cell_text(repo_row[i - 1]) if i <= len(repo_row) else ""
    if header == target:
        print(f"FOUND\t{i}")
        raise SystemExit(0)

# 未找到则在紧凑组件块（从 B 列开始）后追加
for i in range(2, max_len + 2):
    header = cell_text(row[i - 1]) if i <= len(row) else ""
    repo = cell_text(repo_row[i - 1]) if i <= len(repo_row) else ""
    if not header and not repo:
        print(f"MISSING\t{i}")
        raise SystemExit(0)
print(f"MISSING\t{max_len + 1}")
PY
  )
  rm -f "$resp_file"

  status="${result%%$'\t'*}"
  value="${result#*$'\t'}"

  if [[ "$status" == "FOUND" ]]; then
    column_letter "$value"
    return 0
  fi

  if [[ "$status" != "MISSING" ]]; then
    die "find_or_create_component_column: unexpected result: $result"
  fi

  log "Component column ${component_name} not found, creating at column index ${value}"

  meta_resp=$(feishu_api_json "GET" \
    "https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/sheets/query" \
    "$token") || die "query sheet metadata failed"

  column_count=$(python3 - "$sheet_id" "$meta_resp" <<'PY'
import json, sys
sheet_id, resp = sys.argv[1], sys.argv[2]
data = json.loads(resp)
if data.get("code") != 0:
    raise SystemExit(f"query sheets failed: {data}")
for sheet in data.get("data", {}).get("sheets", []):
    if sheet.get("sheet_id") == sheet_id:
        print(sheet.get("grid_properties", {}).get("column_count", 0))
        raise SystemExit(0)
raise SystemExit(f"sheet id not found: {sheet_id}")
PY
  )

  if (( value >= column_count )); then
    resp2=$(feishu_api_json "POST" \
      "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/dimension_range" \
      "$token" \
      "{\"dimension\":{\"sheetId\":\"${sheet_id}\",\"majorDimension\":\"COLUMNS\",\"length\":1}}") || die "append component column failed"
  else
    resp2=$(feishu_api_json "POST" \
      "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/insert_dimension_range" \
      "$token" \
      "{\"dimension\":{\"sheetId\":\"${sheet_id}\",\"majorDimension\":\"COLUMNS\",\"startIndex\":${value},\"endIndex\":$((value + 1))},\"inheritStyle\":\"BEFORE\"}") || die "insert component column failed"
  fi

  python3 - "$resp2" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
if data.get("code") != 0:
    raise SystemExit(f"add component column failed: {data}")
PY

  column_letter "$value"
}

find_date_row() {
  local token="$1"
  local sheet_id="$2"
  local target_date="$3"
  local resp

  resp=$(get_range_values "$token" "${sheet_id}!A4:A2000")

  python3 - "$target_date" "$resp" <<'PY'
import json, sys
target = sys.argv[1]
data = json.loads(sys.argv[2])
if data.get("code") != 0:
    raise SystemExit(f"read date column failed: {data}")
values = data.get("data", {}).get("valueRange", {}).get("values", [])
for idx, row in enumerate(values, start=4):
    if row and str(row[0]).strip() == target:
        print(idx)
        raise SystemExit(0)
print("")
PY
}

prepend_date_row() {
  local token="$1"
  local sheet_id="$2"
  local today="$3"
  local resp

  resp=$(
    feishu_api_json "POST" \
      "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/values_prepend" \
      "$token" \
      "{\"valueRange\":{\"range\":\"${sheet_id}!A4:A4\",\"values\":[[\"${today}\"]]}}"
  )

  python3 - "$resp" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
if data.get("code") != 0:
    raise SystemExit(f"prepend_date_row failed: {data}")
PY
}

update_feishu_cell() {
  local token="$1"
  local sheet_id="$2"
  local sheet_title="$3"
  local component_name="$4"
  local repo_uri="$5"
  local row="$6"
  local tag="$7"
  local component_col

  component_col="$(find_or_create_component_column "$token" "$sheet_id" "$component_name")"
  write_cell "$token" "$sheet_id" "${component_col}1" "$component_name"
  write_cell "$token" "$sheet_id" "${component_col}2" "$repo_uri"
  write_cell "$token" "$sheet_id" "${component_col}${row}" "$tag"

  log "Feishu updated: ${sheet_title}!${component_col}${row} = ${tag} (${component_name})"
}

# =============================================================================
# Build & push
# =============================================================================

build_and_push() {
  local arch_tag="$1"
  local component="$2"
  local dockerfile="$3"
  local image_name

  case "$component" in
    backend)  image_name="${BACKEND_REPOSITORY}:${arch_tag}_${TAG_OVERRIDE:-$TODAY}" ;;
    frontend) image_name="${FRONTEND_REPOSITORY}:${arch_tag}_${TAG_OVERRIDE:-$TODAY}" ;;
    *) die "unknown component: $component" ;;
  esac

  log "Building ${component} (${arch_tag}): ${image_name}"

  if [[ "$DRY_RUN" == "1" ]]; then
    log "[DRY] Would build: docker build -f ${dockerfile} -t ${image_name} ."
    return 0
  fi

  docker build \
    -f "$dockerfile" \
    -t "$image_name" \
    .

  if [[ "$PUSH_IMAGES" == "1" ]]; then
    docker push "$image_name"
    log "Pushed: ${image_name}"
  fi
}

# =============================================================================
# Argument parsing
# =============================================================================

while [[ $# -gt 0 ]]; do
  case "$1" in
    --component)
      case "$2" in
        backend)  BUILD_BACKEND=1; BUILD_FRONTEND=0 ;;
        frontend) BUILD_BACKEND=0; BUILD_FRONTEND=1 ;;
        *) die "unsupported component: $2" ;;
      esac
      shift 2
      ;;
    --no-push)
      PUSH_IMAGES=0
      shift
      ;;
    --no-feishu)
      UPDATE_FEISHU=0
      shift
      ;;
    --feishu-only)
      SKIP_BUILD=1
      PUSH_IMAGES=0
      UPDATE_FEISHU=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      PUSH_IMAGES=0
      UPDATE_FEISHU=0
      shift
      ;;
    --target)
      TARGET="$2"
      shift 2
      ;;
    --sheet)
      TARGET_SHEETS+=("$2")
      shift 2
      ;;
    --tag)
      TAG_OVERRIDE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

require_cmd python3

if [[ "$DRY_RUN" != "1" && "$SKIP_BUILD" != "1" ]]; then
  require_cmd docker
fi
if [[ "$UPDATE_FEISHU" == "1" ]]; then
  require_cmd curl
fi

# =============================================================================
# Architecture detection (参考 weknora)
# =============================================================================

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64)
    ARCH_TAG="amd"
    DEFAULT_SHEETS=("${AMD_SHEETS[@]}")
    ;;
  aarch64|arm64)
    ARCH_TAG="arm"
    DEFAULT_SHEETS=("${ARM_SHEETS[@]}")
    ;;
  *)
    die "unsupported architecture: ${ARCH}"
    ;;
esac

if [[ -n "$TARGET" ]]; then
  case "$TARGET" in
    amd)
      ARCH_TAG="amd"
      ;;
    arm)
      ARCH_TAG="arm"
      ;;
    *)
      die "unsupported --target: ${TARGET}; expected amd or arm"
      ;;
  esac
fi

# 验证 target 与当前机器架构是否匹配（参考 weknora）
if [[ "$DRY_RUN" != "1" && "$SKIP_BUILD" != "1" ]]; then
  case "${ARCH_TAG}:${ARCH}" in
    amd:x86_64|amd:amd64|arm:aarch64|arm:arm64)
      ;;
    *)
      die "Target ${ARCH_TAG} does not match native architecture ${ARCH}. Pass correct --target or run on matching build host."
      ;;
  esac
fi

if [[ ${#TARGET_SHEETS[@]} -eq 0 ]]; then
  TARGET_SHEETS=("${DEFAULT_SHEETS[@]}")
fi

TAG="${ARCH_TAG}_${TAG_OVERRIDE:-$TODAY}"

log "Architecture: ${ARCH}"
log "Target: ${ARCH_TAG}"
log "Tag: ${TAG}"
log "Sheets: ${TARGET_SHEETS[*]}"
log "Components: backend=${BUILD_BACKEND} frontend=${BUILD_FRONTEND}"
log "Push: ${PUSH_IMAGES}  Feishu: ${UPDATE_FEISHU}  DryRun: ${DRY_RUN}"

if [[ "$DRY_RUN" == "1" ]]; then
  exit 0
fi

# =============================================================================
# Build phase
# =============================================================================

if [[ "$SKIP_BUILD" != "1" ]]; then
  if [[ "$BUILD_BACKEND" == "1" ]]; then
    build_and_push "$ARCH_TAG" "backend" "docker/Dockerfile"
  fi
  if [[ "$BUILD_FRONTEND" == "1" ]]; then
    build_and_push "$ARCH_TAG" "frontend" "frontend/Dockerfile"
  fi
fi

# =============================================================================
# Feishu write phase
# =============================================================================

if [[ "$UPDATE_FEISHU" == "1" ]]; then
  [[ -f "$FEISHU_CONFIG_FILE" ]] || die "Feishu config not found: $FEISHU_CONFIG_FILE"

  FEISHU_APP_ID="$(read_feishu_field "feishu_app_id")"
  FEISHU_APP_SECRET="$(read_feishu_field "feishu_app_secret")"
  [[ -n "$FEISHU_APP_ID" && -n "$FEISHU_APP_SECRET" ]] || die "feishu_app_id or feishu_app_secret missing in $FEISHU_CONFIG_FILE"

  for sheet_title in "${TARGET_SHEETS[@]}"; do
    token="$(get_feishu_token "$FEISHU_APP_ID" "$FEISHU_APP_SECRET")"
    sheet_id="$(get_sheet_id_by_title "$token" "$sheet_title")"
    log "Resolved sheet: ${sheet_title} -> ${sheet_id}"

    token="$(get_feishu_token "$FEISHU_APP_ID" "$FEISHU_APP_SECRET")"
    date_row="$(find_date_row "$token" "$sheet_id" "$TODAY")"
    if [[ -z "$date_row" ]]; then
      log "Date ${TODAY} not found in ${sheet_title}, creating a new row at top of data area"
      token="$(get_feishu_token "$FEISHU_APP_ID" "$FEISHU_APP_SECRET")"
      prepend_date_row "$token" "$sheet_id" "$TODAY"
      date_row=4
    else
      log "Date ${TODAY} already exists in ${sheet_title} at row ${date_row}"
    fi

    if [[ "$BUILD_BACKEND" == "1" ]]; then
      token="$(get_feishu_token "$FEISHU_APP_ID" "$FEISHU_APP_SECRET")"
      update_feishu_cell "$token" "$sheet_id" "$sheet_title" \
        "$BACKEND_COMPONENT_NAME" "$BACKEND_REPOSITORY" "$date_row" "$TAG"
    fi
    if [[ "$BUILD_FRONTEND" == "1" ]]; then
      token="$(get_feishu_token "$FEISHU_APP_ID" "$FEISHU_APP_SECRET")"
      update_feishu_cell "$token" "$sheet_id" "$sheet_title" \
        "$FRONTEND_COMPONENT_NAME" "$FRONTEND_REPOSITORY" "$date_row" "$TAG"
    fi
  done
fi

log "Done."
