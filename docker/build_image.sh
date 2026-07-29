#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# desensitize build/push script
# =============================================================================
# 在构建机本地执行：按 --sheet 显式指定 profile/sheet，构建镜像、推送 SWR、
# 将 tag 写入飞书发布表对应 sheet。
#
# 使用方式（在构建机上执行）:
#   tc232:  ./docker/build_image.sh --sheet AMD_with_cuda --sheet AMD_with_mxn100
#   tc81:   ./docker/build_image.sh --sheet ARM_with_cuda --sheet ARM_without_cuda \
#                                   --sheet l4t --sheet thor_spark
#
# 飞书表格结构（与 weknora/lexai 一致）:
#   - 第 1 行：服务名（镜像本名，如 desensitize-backend）
#   - 第 2 行：组件（镜像仓库地址，如 swr.../ictrek/desensitize-backend）
#   - 第 3 行：冻结分隔（更新记录）
#   - 第 4 行起：日期行，每个日期一行，写入当天对应镜像 tag
#   - 列不存在时向右 append 新列；日期不存在时在 A4 prepend 新行
# =============================================================================

cd "$(dirname "$0")/.."

FEISHU_CONFIG_FILE="${FEISHU_CONFIG_FILE:-${HOME}/.feishu.json}"
FEISHU_SPREADSHEET_TOKEN="${FEISHU_SPREADSHEET_TOKEN:-Htotsn3oahO1zxt73YMcaB1zn8e}"
REGISTRY="${REGISTRY:-swr.cn-southwest-2.myhuaweicloud.com/ictrek}"

BACKEND_REPOSITORY="${REGISTRY}/desensitize-backend"
FRONTEND_REPOSITORY="${REGISTRY}/desensitize-frontend"

# sheet -> 镜像 tag 前缀
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
BUILD_ENGINE="${DESENSITIZE_BUILD_ENGINE:-auto}"

TARGET_SHEETS=()

log() { echo "[INFO] $*"; }
err() { echo "[ERROR] $*" >&2; }
die() { err "$*"; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

configure_build_engine() {
  case "$BUILD_ENGINE" in
    auto)
      if docker buildx version >/dev/null 2>&1; then
        BUILD_ENGINE="buildx"
      else
        BUILD_ENGINE="docker"
      fi
      ;;
    buildx)
      docker buildx version >/dev/null 2>&1 || die "DESENSITIZE_BUILD_ENGINE=buildx but docker buildx is unavailable"
      ;;
    docker)
      ;;
    *)
      die "Unsupported DESENSITIZE_BUILD_ENGINE=${BUILD_ENGINE}; expected auto, buildx, or docker"
      ;;
  esac
}

docker_build_image() {
  if [[ "$BUILD_ENGINE" == "buildx" ]]; then
    docker buildx build --load --provenance=false --sbom=false "$@"
  else
    docker build "$@"
  fi
}

usage() {
  cat <<'EOF'
Usage: ./docker/build_image.sh --sheet SHEET [--sheet SHEET ...] [options]

Build desensitize images for the specified profile sheets and record tags in Feishu.

Profiles:
  AMD:      AMD_with_cuda, AMD_with_mxn100
  ARM:      ARM_with_cuda, ARM_without_cuda, l4t, thor_spark, SOPHON_bm1688

Options:
  --sheet SHEET            Feishu sheet / profile (can be repeated)
  --component backend      Build only backend
  --component frontend     Build only frontend
  --no-push                Build locally without docker push
  --no-feishu              Do not update Feishu
  --feishu-only            Only write tags to Feishu (no build/push)
  --dry-run                Print plan without executing
  --tag TAG                Override tag (default: <sheet>_<YYYYMMDD>)
  -h, --help               Show this help

Environment:
  FEISHU_CONFIG_FILE       Defaults to ~/.feishu.json
  REGISTRY                 SWR registry prefix
EOF
}

# =============================================================================
# Feishu helpers
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

  resp=$(feishu_api_json "GET" \
    "https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/sheets/query" \
    "$token")

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

  resp=$(feishu_api_json "PUT" \
    "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/values" \
    "$token" \
    "{\"valueRange\":{\"range\":\"${sheet_id}!${cell}:${cell}\",\"values\":[[\"${value}\"]]}}")

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
  local service_name="$3"
  local resp_file

  resp_file="$(mktemp)"
  get_range_values "$token" "${sheet_id}!A1:ZZ2" > "$resp_file"

  python3 - "$service_name" "$resp_file" <<'PY'
import json, sys
target = sys.argv[1]
with open(sys.argv[2], "r", encoding="utf-8") as f:
    data = json.load(f)
if data.get("code") != 0:
    raise SystemExit(f"read header failed: {data}")
values = data.get("data", {}).get("valueRange", {}).get("values", [])
row = values[0] if values else []
repo_row = values[1] if len(values) > 1 else []

def text(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return str(v.get("text") or v.get("link") or "").strip()
    if isinstance(v, list):
        return "".join(text(x) for x in v).strip()
    return str(v).strip()

def col(n):
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s

max_len = max(len(row), len(repo_row))

# search entire header range first
for i in range(2, max_len + 1):
    header = text(row[i - 1]) if i <= len(row) else ""
    if header == target:
        print(col(i))
        raise SystemExit(0)

# find first empty slot after compact block, or append
for i in range(2, max_len + 2):
    header = text(row[i - 1]) if i <= len(row) else ""
    repo = text(repo_row[i - 1]) if i <= len(repo_row) else ""
    if not header and not repo:
        print(col(i))
        raise SystemExit(0)

print(col(max_len + 1))
PY

  rm -f "$resp_file"
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

  resp=$(feishu_api_json "POST" \
    "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/values_prepend" \
    "$token" \
    "{\"valueRange\":{\"range\":\"${sheet_id}!A4:A4\",\"values\":[[\"${today}\"]]}}")

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
  local service_name="$4"      # e.g. desensitize-backend
  local repo_uri="$5"
  local row="$6"
  local tag="$7"
  local component_col

  component_col="$(find_or_create_component_column "$token" "$sheet_id" "$service_name")"
  write_cell "$token" "$sheet_id" "${component_col}1" "$service_name"
  write_cell "$token" "$sheet_id" "${component_col}2" "$repo_uri"
  write_cell "$token" "$sheet_id" "${component_col}${row}" "$tag"

  log "Feishu updated: ${sheet_title}!${component_col}${row} = ${tag} (${service_name})"
}

# =============================================================================
# Build & push
# =============================================================================

resolve_dockerfile() {
  local component="$1"
  local sheet="$2"
  local preferred

  if [[ "$component" == "frontend" ]]; then
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
    log "[DRY] Would build: docker buildx build --load -f ${dockerfile} -t ${image_name} ."
    return 0
  fi

  docker_build_image \
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
  die "at least one --sheet is required"
fi

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
# Build phase
# =============================================================================

if [[ "$SKIP_BUILD" != "1" ]]; then
  configure_build_engine
  log "BUILD_ENGINE=${BUILD_ENGINE}"

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
        "desensitize-backend" "$BACKEND_REPOSITORY" "$date_row" "$tag"
    fi
    if [[ "$BUILD_FRONTEND" == "1" ]]; then
      token="$(get_feishu_token "$FEISHU_APP_ID" "$FEISHU_APP_SECRET")"
      update_feishu_cell "$token" "$sheet_id" "$sheet" \
        "desensitize-frontend" "$FRONTEND_REPOSITORY" "$date_row" "$tag"
    fi
  done
fi

log "Done."
