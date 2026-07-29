#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# desensitize build/push script
# =============================================================================
# 通过 SSH 在远程构建机上分别构建 amd / l4t / arm 三种镜像，推送到 SWR，
# 然后参考 weknora/model_hub 的写飞书逻辑，将镜像标签写入飞书发布表。
#
# 构建矩阵（与 docker-compose profile 对应关系）:
#   tc232  → amd 镜像  → 供 amd / amd-without-cuda profile 使用（同一镜像）
#   tc192  → l4t 镜像  → 供 l4t profile 使用
#   tc81   → arm 镜像  → 供 arm / arm-without-cuda / thor-spark profile 使用（同一镜像）
#
# 说明:
#   - amd 与 amd-without-cuda 共用同一个 amd 镜像，差别仅在 docker-compose
#     profile 是否声明 runtime: nvidia
#   - arm 与 arm-without-cuda 共用同一个 arm 镜像；thor-spark 也复用 arm 镜像
#     （当前纯正则阶段无 CUDA 依赖，thor 与 arm 用同一镜像即可）
#   - 后续若引入 PyTorch NER，可在此脚本中拆分 thor / l4t 独立镜像
#
# 飞书写入逻辑（参考 weknora/build_image.sh）:
#   - 每个组件占一列（desensitize_backend / desensitize_frontend）
#   - 第 1 行写组件名，第 2 行写镜像仓库地址
#   - 第 4 行起按日期递增，每个日期行写入当天对应组件的镜像 tag
#   - 若组件列不存在，自动在末尾追加列；若当天日期行不存在，自动在最上方插入
#
# Usage:
#   ./build_image.sh                          # 构建全部 (amd + l4t + arm)
#   ./build_image.sh --target amd             # 只构建 amd
#   ./build_image.sh --target l4t             # 只构建 l4t
#   ./build_image.sh --target arm             # 只构建 arm (覆盖 thor-spark)
#   ./build_image.sh --component backend      # 只构建 backend
#   ./build_image.sh --component frontend     # 只构建 frontend
#   ./build_image.sh --no-push                # 构建但不推送
#   ./build_image.sh --no-feishu              # 不写飞书
#   ./build_image.sh --feishu-only             # 不构建，仅根据已知 tag 写飞书
#   ./build_image.sh --dry-run                # 只打印计划
#   ./build_image.sh --tag 20260729           # 覆盖默认 tag
# =============================================================================

cd "$(dirname "$0")/.."

FEISHU_CONFIG_FILE="${FEISHU_CONFIG_FILE:-${HOME}/.feishu.json}"
FEISHU_SPREADSHEET_TOKEN="${FEISHU_SPREADSHEET_TOKEN:-Htotsn3oahO1zxt73YMcaB1zn8e}"
REGISTRY="${REGISTRY:-swr.cn-southwest-2.myhuaweicloud.com/ictrek}"

BACKEND_REPOSITORY="${REGISTRY}/desensitize-backend"
FRONTEND_REPOSITORY="${REGISTRY}/desensitize-frontend"
BACKEND_COMPONENT_NAME="desensitize_backend"
FRONTEND_COMPONENT_NAME="desensitize_frontend"

# 远程构建机配置
AMD_HOST="${AMD_HOST:-tc232}"
L4T_HOST="${L4T_HOST:-tc192}"
ARM_HOST="${ARM_HOST:-tc81}"
# 远程机构上 desensitize 仓库的路径
REMOTE_REPO_DIR="${REMOTE_REPO_DIR:-/data/build/desensitize}"
# 远程机 git 分支（默认跟随 origin/main）
REMOTE_BRANCH="${REMOTE_BRANCH:-main}"

# 飞书各架构对应的 sheet 名（与 package.sh 中 PROFILES 保持一致）
AMD_SHEETS=("AMD_with_cuda")
L4T_SHEETS=("l4t")
ARM_SHEETS=("ARM_with_cuda" "ARM_without_cuda" "thor_spark")

TODAY="$(date +%Y%m%d)"
TAG_OVERRIDE=""

BUILD_AMD=1
BUILD_L4T=1
BUILD_ARM=1
BUILD_BACKEND=1
BUILD_FRONTEND=1
PUSH_IMAGES=1
UPDATE_FEISHU=1
DRY_RUN=0
SKIP_BUILD=0

log() { echo "[INFO] $*"; }
err() { echo "[ERROR] $*" >&2; }
die() { err "$*"; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}

usage() {
  cat <<'EOF'
Usage: ./build_image.sh [options]

Build desensitize images on remote hosts and record tags in Feishu.

Build targets (default: all):
  --target amd       Build only amd image on tc232 (for amd / amd-without-cuda profiles)
  --target l4t       Build only l4t image on tc192 (for l4t profile)
  --target arm       Build only arm image on tc81 (for arm / arm-without-cuda / thor-spark profiles)

Component selection (default: both):
  --component backend      Build only backend image
  --component frontend     Build only frontend image

Flags:
  --no-push          Build locally on remote host without docker push
  --no-feishu        Do not update Feishu after push
  --feishu-only      Do not build or push; only write selected tags to Feishu
  --dry-run          Print plan without building, pushing, or writing Feishu
  --tag TAG          Override the generated tag (default: <arch>_<YYYYMMDD>)

Environment overrides:
  AMD_HOST           Default tc232
  L4T_HOST           Default tc192
  ARM_HOST           Default tc81
  REMOTE_REPO_DIR    Remote path to desensitize repo (default /data/build/desensitize)
  REMOTE_BRANCH      Remote git branch (default main)
  REGISTRY           SWR registry prefix
  FEISHU_CONFIG_FILE  Default ~/.feishu.json
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

# 查找或创建组件列（参考 weknora 的 find_or_create_component_column）
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

  # 检查是否需要扩展 sheet 列数
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

  cell=$(column_letter "$value")
  # 写入第 1 行的组件名和第 2 行的镜像仓库地址（由调用方传入）
  echo "$cell"
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

# 将单个架构的 tag 写入对应的所有 sheet
write_arch_tags_to_feishu() {
  local arch_tag="$1"
  shift
  local sheets=("$@")
  local app_id app_secret token sheet_id date_row sheet_title

  [[ -f "$FEISHU_CONFIG_FILE" ]] || die "Feishu config not found: $FEISHU_CONFIG_FILE"

  app_id="$(read_feishu_field "feishu_app_id")"
  app_secret="$(read_feishu_field "feishu_app_secret")"
  [[ -n "$app_id" && -n "$app_secret" ]] || die "feishu_app_id or feishu_app_secret missing in $FEISHU_CONFIG_FILE"

  for sheet_title in "${sheets[@]}"; do
    token="$(get_feishu_token "$app_id" "$app_secret")"
    sheet_id="$(get_sheet_id_by_title "$token" "$sheet_title")"
    log "Resolved sheet: ${sheet_title} -> ${sheet_id}"

    token="$(get_feishu_token "$app_id" "$app_secret")"
    date_row="$(find_date_row "$token" "$sheet_id" "$TODAY")"
    if [[ -z "$date_row" ]]; then
      log "Date ${TODAY} not found in ${sheet_title}, creating a new row at top of data area"
      token="$(get_feishu_token "$app_id" "$app_secret")"
      prepend_date_row "$token" "$sheet_id" "$TODAY"
      date_row=4
    else
      log "Date ${TODAY} already exists in ${sheet_title} at row ${date_row}"
    fi

    if [[ "$BUILD_BACKEND" == "1" ]]; then
      token="$(get_feishu_token "$app_id" "$app_secret")"
      update_feishu_cell "$token" "$sheet_id" "$sheet_title" \
        "$BACKEND_COMPONENT_NAME" "$BACKEND_REPOSITORY" "$date_row" "${arch_tag}_${TAG_OVERRIDE:-$TODAY}"
    fi
    if [[ "$BUILD_FRONTEND" == "1" ]]; then
      token="$(get_feishu_token "$app_id" "$app_secret")"
      update_feishu_cell "$token" "$sheet_id" "$sheet_title" \
        "$FRONTEND_COMPONENT_NAME" "$FRONTEND_REPOSITORY" "$date_row" "${arch_tag}_${TAG_OVERRIDE:-$TODAY}"
    fi
  done
}

# =============================================================================
# Remote build via SSH
# =============================================================================

remote_build_and_push() {
  local host="$1"
  local arch_tag="$2"
  local component="$3"
  local dockerfile="$4"
  local image_name

  case "$component" in
    backend)  image_name="${BACKEND_REPOSITORY}:${arch_tag}_${TAG_OVERRIDE:-$TODAY}" ;;
    frontend) image_name="${FRONTEND_REPOSITORY}:${arch_tag}_${TAG_OVERRIDE:-$TODAY}" ;;
    *) die "unknown component: $component" ;;
  esac

  log "Building ${component} (${arch_tag}) on ${host}: ${image_name}"

  local push_cmd=""
  if [[ "$PUSH_IMAGES" == "1" ]]; then
    push_cmd="&& docker push ${image_name}"
  fi

  # 在远程机上拉取最新代码并构建/推送
  # 远程机需要预先配置好 docker login 凭证和 github SSH key
  ssh "${SSH_OPTS:-}" "$host" "set -euo pipefail; \
    if [[ ! -d ${REMOTE_REPO_DIR} ]]; then \
      git clone --recurse-submodules git@github.com:ictrektech/desensitize.git ${REMOTE_REPO_DIR}; \
    fi; \
    cd ${REMOTE_REPO_DIR} && \
    git fetch --quiet origin && \
    git checkout --quiet ${REMOTE_BRANCH} && \
    git reset --hard origin/${REMOTE_BRANCH} && \
    git submodule update --init --recursive && \
    docker build -f ${dockerfile} -t ${image_name} . ${push_cmd}"

  log "Done: ${image_name} on ${host}"
}

# =============================================================================
# Argument parsing
# =============================================================================

TARGETS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGETS+=("$2")
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

if [[ ${#TARGETS[@]} -gt 0 ]]; then
  BUILD_AMD=0
  BUILD_L4T=0
  BUILD_ARM=0
  for t in "${TARGETS[@]}"; do
    case "$t" in
      amd) BUILD_AMD=1 ;;
      l4t) BUILD_L4T=1 ;;
      arm) BUILD_ARM=1 ;;
      *) die "unsupported target: $t (expected amd / l4t / arm)" ;;
    esac
  done
fi

require_cmd python3

if [[ "$DRY_RUN" != "1" && "$SKIP_BUILD" != "1" ]]; then
  require_cmd ssh
fi
if [[ "$UPDATE_FEISHU" == "1" ]]; then
  require_cmd curl
fi

log "Targets: amd=${BUILD_AMD} l4t=${BUILD_L4T} arm=${BUILD_ARM}"
log "Components: backend=${BUILD_BACKEND} frontend=${BUILD_FRONTEND}"
log "Tag suffix: ${TAG_OVERRIDE:-$TODAY}"
log "Push: ${PUSH_IMAGES}  Feishu: ${UPDATE_FEISHU}  DryRun: ${DRY_RUN}"

if [[ "$DRY_RUN" == "1" ]]; then
  [[ "$BUILD_AMD" == "1" ]] && log "[DRY] Would build amd on ${AMD_HOST} -> tag amd_${TAG_OVERRIDE:-$TODAY}"
  [[ "$BUILD_L4T" == "1" ]] && log "[DRY] Would build l4t on ${L4T_HOST} -> tag l4t_${TAG_OVERRIDE:-$TODAY}"
  [[ "$BUILD_ARM" == "1" ]] && log "[DRY] Would build arm on ${ARM_HOST} -> tag arm_${TAG_OVERRIDE:-$TODAY}"
  [[ "$UPDATE_FEISHU" == "1" ]] && log "[DRY] Would write tags to Feishu sheets"
  exit 0
fi

# =============================================================================
# Build phase
# =============================================================================

if [[ "$SKIP_BUILD" != "1" ]]; then
  if [[ "$BUILD_AMD" == "1" ]]; then
    log "=== AMD build on ${AMD_HOST} ==="
    [[ "$BUILD_BACKEND" == "1" ]]  && remote_build_and_push "$AMD_HOST" "amd" "backend"  "docker/Dockerfile"
    [[ "$BUILD_FRONTEND" == "1" ]] && remote_build_and_push "$AMD_HOST" "amd" "frontend" "frontend/Dockerfile"
  fi

  if [[ "$BUILD_L4T" == "1" ]]; then
    log "=== L4T build on ${L4T_HOST} ==="
    [[ "$BUILD_BACKEND" == "1" ]]  && remote_build_and_push "$L4T_HOST" "l4t" "backend"  "docker/Dockerfile"
    [[ "$BUILD_FRONTEND" == "1" ]] && remote_build_and_push "$L4T_HOST" "l4t" "frontend" "frontend/Dockerfile"
  fi

  if [[ "$BUILD_ARM" == "1" ]]; then
    log "=== ARM build on ${ARM_HOST} (covers arm / arm-without-cuda / thor-spark) ==="
    [[ "$BUILD_BACKEND" == "1" ]]  && remote_build_and_push "$ARM_HOST" "arm" "backend"  "docker/Dockerfile"
    [[ "$BUILD_FRONTEND" == "1" ]] && remote_build_and_push "$ARM_HOST" "arm" "frontend" "frontend/Dockerfile"
  fi
fi

# =============================================================================
# Feishu write phase
# =============================================================================

if [[ "$UPDATE_FEISHU" == "1" ]]; then
  # amd 镜像 -> AMD_with_cuda sheet (供 amd / amd-without-cuda profile 复用)
  if [[ "$BUILD_AMD" == "1" ]]; then
    log "=== Writing amd tags to Feishu: ${AMD_SHEETS[*]} ==="
    write_arch_tags_to_feishu "amd" "${AMD_SHEETS[@]}"
  fi

  # l4t 镜像 -> l4t sheet
  if [[ "$BUILD_L4T" == "1" ]]; then
    log "=== Writing l4t tags to Feishu: ${L4T_SHEETS[*]} ==="
    write_arch_tags_to_feishu "l4t" "${L4T_SHEETS[@]}"
  fi

  # arm 镜像 -> ARM_with_cuda / ARM_without_cuda / thor_spark sheets
  # (三个 profile 共用同一个 arm 镜像，因此写到三个 sheet)
  if [[ "$BUILD_ARM" == "1" ]]; then
    log "=== Writing arm tags to Feishu: ${ARM_SHEETS[*]} ==="
    write_arch_tags_to_feishu "arm" "${ARM_SHEETS[@]}"
  fi
fi

log "Done."
