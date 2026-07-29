#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# desensitize build/push script
# =============================================================================
# 在构建机本地执行：按 --sheet 指定的每个 profile/sheet 单独构建一份镜像，
# 推送到 SWR，并将 tag 写入飞书发布表对应 sheet。
#
# 与 model_hub/weknora 的区别：
#   desensitize 有 6 个 profile（amd / amd-without-cuda / arm / arm-without-cuda
#   / l4t / thor-spark），未来不同 profile 拉取的基镜像会因 pytorch 运行环境
#   差异而不同，因此每次调用按 sheet 显式选择要构建/写入的 profile，
#   每个 sheet 对应一份独立的镜像 tag，而不是共用一个 tag。
#
# 使用方式（在构建机上执行）:
#   tc232:  ./docker/build_image.sh --sheet AMD_with_cuda
#   tc232:  ./docker/build_image.sh --sheet AMD_with_mxn100
#   tc192:  ./docker/build_image.sh --sheet l4t
#   tc81:   ./docker/build_image.sh --sheet ARM_with_cuda
#   tc81:   ./docker/build_image.sh --sheet ARM_without_cuda
#   tc81:   ./docker/build_image.sh --sheet thor_spark
#   一次性多个 sheet:
#           ./docker/build_image.sh --sheet ARM_with_cuda --sheet ARM_without_cuda \
#                                   --sheet thor_spark
#
# profile -> Dockerfile 映射（每个 profile 可独立指定 Dockerfile，
# 缺失则回退到默认 docker/Dockerfile）:
#   AMD_with_cuda       -> docker/Dockerfile.amd          (或 docker/Dockerfile)
#   AMD_with_mxn100     -> docker/Dockerfile.amd_mxn100
#   ARM_with_cuda       -> docker/Dockerfile.arm
#   ARM_without_cuda    -> docker/Dockerfile.arm
#   l4t                 -> docker/Dockerfile.l4t
#   thor_spark          -> docker/Dockerfile.thor_spark
#   SOPHON_bm1688       -> docker/Dockerfile.sophon
#
# 镜像 tag 格式：<sheet_to_tag>_<YYYYMMDD>，例如 l4t_20260729、thor_spark_20260729。
# 飞书写入：每个 sheet 一行当天日期，<sheet>!desensitize_backend 列写后端 tag，
#           <sheet>!desensitize_frontend 列写前端 tag。
# =============================================================================

cd "$(dirname "$0")/.."

FEISHU_CONFIG_FILE="${FEISHU_CONFIG_FILE:-${HOME}/.feishu.json}"
FEISHU_SPREADSHEET_TOKEN="${FEISHU_SPREADSHEET_TOKEN:-Htotsn3oahO1zxt73YMcaB1zn8e}"
REGISTRY="${REGISTRY:-swr.cn-southwest-2.myhuaweicloud.com/ictrek}"

BACKEND_REPOSITORY="${REGISTRY}/desensitize-backend"
FRONTEND_REPOSITORY="${REGISTRY}/desensitize-frontend"
BACKEND_COMPONENT_NAME="desensitize_backend"
FRONTEND_COMPONENT_NAME="desensitize_frontend"

# sheet -> 镜像 tag 前缀（注意 ARM_with_cuda / ARM_without_cuda 共用同一份 arm 镜像）
sheet_to_tag_prefix() {
  case "$1" in
    AMD_with_cuda)    echo "amd" ;;
    AMD_with_mxn100)  echo "amd_mxn100" ;;
    ARM_with_cuda)    echo "arm" ;;
    ARM_without_cuda) echo "arm" ;;
    l4t)              echo "l4t" ;;
    thor_spark)       echo "thor_spark" ;;
    SOPHON_bm1688)    echo "sophon" ;;
    *) return 1 ;;
  esac
}

# sheet -> 期望的 backend Dockerfile；缺失则回退到默认 docker/Dockerfile
sheet_to_dockerfile() {
  case "$1" in
    AMD_with_cuda)    echo "docker/Dockerfile.amd" ;;
    AMD_with_mxn100)  echo "docker/Dockerfile.amd_mxn100" ;;
    ARM_with_cuda)    echo "docker/Dockerfile.arm" ;;
    ARM_without_cuda) echo "docker/Dockerfile.arm" ;;
    l4t)              echo "docker/Dockerfile.l4t" ;;
    thor_spark)       echo "docker/Dockerfile.thor_spark" ;;
    SOPHON_bm1688)    echo "docker/Dockerfile.sophon" ;;
    *) return 1 ;;
  esac
}

DEFAULT_BACKEND_DOCKERFILE="docker/Dockerfile"
DEFAULT_FRONTEND_DOCKERFILE="frontend/Dockerfile"

VALID_SHEETS=("AMD_with_cuda" "AMD_with_mxn100" "ARM_with_cuda" "ARM_without_cuda" "l4t" "thor_spark" "SOPHON_bm1688")

TODAY="$(date +%Y%m%d)"
TAG_OVERRIDE=""

BUILD_BACKEND=1
BUILD_FRONTEND=1
PUSH_IMAGES=1
UPDATE_FEISHU=1
DRY_RUN=0
SKIP_BUILD=0

TARGET_SHEETS=()

log() { echo "[INFO] $*"; }
err() { echo "[ERROR] $*" >&2; }
die() { err "$*"; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

usage() {
  cat <<'EOF'
Usage: ./docker/build_image.sh --sheet SHEET [--sheet SHEET ...] [options]

Build desensitize images for the specified profile sheets and record tags in Feishu.

Profiles (must match at least one --sheet):
  AMD:      AMD_with_cuda, AMD_with_mxn100
  ARM:      ARM_with_cuda, ARM_without_cuda, l4t, thor_spark, SOPHON_bm1688

Options:
  --sheet SHEET            Feishu sheet / profile to build (can be repeated)
  --component backend      Build only backend image
  --component frontend     Build only frontend image
  --no-push                Build locally without docker push
  --no-feishu              Do not update Feishu after push
  --feishu-only            Do not build or push; only write tags to Feishu
  --dry-run                Print plan without building, pushing, or writing Feishu
  --tag TAG                Override the generated tag (default: <sheet>_<YYYYMMDD>)
  -h, --help               Show this help

Environment:
  FEISHU_CONFIG_FILE       Defaults to ~/.feishu.json
  REGISTRY                 SWR registry prefix

Notes:
  - Build host must match the profile architecture:
      AMD_with_cuda / AMD_with_mxn100 -> x86_64 host (e.g. tc232)
      ARM_with_cuda / ARM_without_cuda / l4t / thor_spark / SOPHON_bm1688 -> aarch64 host (e.g. tc81, tc192)
  - The script intentionally does not auto-detect architecture because each
    profile may pull a different base image (pytorch runtime differs).
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

for i in range(2, max_len + 1):
    header = cell_text(row[i - 1]) if i <= len(row) else ""
    repo = cell_text(repo_row[i - 1]) if i <= len(repo_row) else ""
    if header == target:
        print(f"FOUND\t{i}")
        raise SystemExit(0)

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

resolve_dockerfile() {
  local component="$1"   # backend | frontend
  local sheet="$2"
  local preferred

  if [[ "$component" == "frontend" ]]; then
    # frontend 暂不按 sheet 拆分，复用同一个 Dockerfile
    echo "$DEFAULT_FRONTEND_DOCKERFILE"
    return 0
  fi

  preferred="$(sheet_to_dockerfile "$sheet" 2>/dev/null || true)"
  if [[ -n "$preferred" && -f "$preferred" ]]; then
    echo "$preferred"
    return 0
  fi

  echo "$DEFAULT_BACKEND_DOCKERFILE"
}

build_and_push() {
  local sheet="$1"
  local component="$2"
  local dockerfile="$3"
  local tag_prefix="$4"
  local tag="${tag_prefix}_${TAG_OVERRIDE:-$TODAY}"
  local image_name

  case "$component" in
    backend)  image_name="${BACKEND_REPOSITORY}:${tag}" ;;
    frontend) image_name="${FRONTEND_REPOSITORY}:${tag}" ;;
    *) die "unknown component: $component" ;;
  esac

  log "Building ${component} (${sheet}, tag=${tag}): ${image_name} via ${dockerfile}"

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
    --sheet)
      TARGET_SHEETS+=("$2")
      shift 2
      ;;
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

if [[ ${#TARGET_SHEETS[@]} -eq 0 ]]; then
  usage
  die "at least one --sheet is required (script does not auto-detect architecture because each profile may need a different base image)"
fi

# 校验 sheet 合法
for sheet in "${TARGET_SHEETS[@]}"; do
  valid=0
  for v in "${VALID_SHEETS[@]}"; do
    [[ "$v" == "$sheet" ]] && valid=1 && break
  done
  [[ "$valid" == "1" ]] || die "unknown sheet: ${sheet}; expected one of: ${VALID_SHEETS[*]}"
done

log "Sheets: ${TARGET_SHEETS[*]}"
log "Components: backend=${BUILD_BACKEND} frontend=${BUILD_FRONTEND}"
log "Push: ${PUSH_IMAGES}  Feishu: ${UPDATE_FEISHU}  DryRun: ${DRY_RUN}"

# =============================================================================
# Build phase: 每个 sheet 单独构建一份镜像（可能 Dockerfile 不同）
# =============================================================================

if [[ "$SKIP_BUILD" != "1" ]]; then
  for sheet in "${TARGET_SHEETS[@]}"; do
    tag_prefix="$(sheet_to_tag_prefix "$sheet")"
    if [[ -z "$tag_prefix" ]]; then
      die "no tag prefix mapping for sheet: ${sheet}"
    fi
    if [[ "$BUILD_BACKEND" == "1" ]]; then
      df="$(resolve_dockerfile backend "$sheet")"
      build_and_push "$sheet" "backend" "$df" "$tag_prefix"
    fi
    if [[ "$BUILD_FRONTEND" == "1" ]]; then
      df="$(resolve_dockerfile frontend "$sheet")"
      build_and_push "$sheet" "frontend" "$df" "$tag_prefix"
    fi
  done
fi

# =============================================================================
# Feishu write phase
# =============================================================================

if [[ "$UPDATE_FEISHU" == "1" ]]; then
  [[ -f "$FEISHU_CONFIG_FILE" ]] || die "Feishu config not found: $FEISHU_CONFIG_FILE"

  FEISHU_APP_ID="$(read_feishu_field "feishu_app_id")"
  FEISHU_APP_SECRET="$(read_feishu_field "feishu_app_secret")"
  [[ -n "$FEISHU_APP_ID" && -n "$FEISHU_APP_SECRET" ]] || die "feishu_app_id or feishu_app_secret missing in $FEISHU_CONFIG_FILE"

  for sheet in "${TARGET_SHEETS[@]}"; do
    tag_prefix="$(sheet_to_tag_prefix "$sheet")"
    tag="${tag_prefix}_${TAG_OVERRIDE:-$TODAY}"

    token="$(get_feishu_token "$FEISHU_APP_ID" "$FEISHU_APP_SECRET")"
    sheet_id="$(get_sheet_id_by_title "$token" "$sheet")"
    log "Resolved sheet: ${sheet} -> ${sheet_id}"

    token="$(get_feishu_token "$FEISHU_APP_ID" "$FEISHU_APP_SECRET")"
    date_row="$(find_date_row "$token" "$sheet_id" "$TODAY")"
    if [[ -z "$date_row" ]]; then
      log "Date ${TODAY} not found in ${sheet}, creating a new row at top of data area"
      token="$(get_feishu_token "$FEISHU_APP_ID" "$FEISHU_APP_SECRET")"
      prepend_date_row "$token" "$sheet_id" "$TODAY"
      date_row=4
    else
      log "Date ${TODAY} already exists in ${sheet} at row ${date_row}"
    fi

    if [[ "$BUILD_BACKEND" == "1" ]]; then
      token="$(get_feishu_token "$FEISHU_APP_ID" "$FEISHU_APP_SECRET")"
      update_feishu_cell "$token" "$sheet_id" "$sheet" \
        "$BACKEND_COMPONENT_NAME" "$BACKEND_REPOSITORY" "$date_row" "$tag"
    fi
    if [[ "$BUILD_FRONTEND" == "1" ]]; then
      token="$(get_feishu_token "$FEISHU_APP_ID" "$FEISHU_APP_SECRET")"
      update_feishu_cell "$token" "$sheet_id" "$sheet" \
        "$FRONTEND_COMPONENT_NAME" "$FRONTEND_REPOSITORY" "$date_row" "$tag"
    fi
  done
fi

log "Done."
