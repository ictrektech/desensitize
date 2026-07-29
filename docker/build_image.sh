#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# desensitize build/push script
# Builds desensitize backend/frontend images, pushes them to SWR.
#
# Usage:
#   ./build_image.sh
#   ./build_image.sh --registry myregistry.com/myorg
#   ./build_image.sh --component backend
#   ./build_image.sh --component frontend
# =============================================================================

cd "$(dirname "$0")/.."

FEISHU_CONFIG_FILE="${HOME}/.feishu.json"
FEISHU_SPREADSHEET_TOKEN="Htotsn3oahO1zxt73YMcaB1zn8e"
REGISTRY="swr.cn-southwest-2.myhuaweicloud.com/ictrek"

BACKEND_REPOSITORY="${REGISTRY}/desensitize-backend"
FRONTEND_REPOSITORY="${REGISTRY}/desensitize-frontend"

TODAY="$(date +%Y%m%d)"
TAG="${TODAY}"

COMPONENT=""  # empty = build both

log() { echo "[INFO] $*"; }
err() { echo "[ERROR] $*" >&2; }
die() { err "$*"; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --registry) REGISTRY="$2"; shift 2 ;;
      --component) COMPONENT="$2"; shift 2 ;;
      --tag) TAG="$2"; shift 2 ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  BACKEND_REPOSITORY="${REGISTRY}/desensitize-backend"
  FRONTEND_REPOSITORY="${REGISTRY}/desensitize-frontend"
}

build_and_push_backend() {
  local arch="$1"
  local image="${BACKEND_REPOSITORY}:${arch}_${TAG}"

  log "Building backend image: ${image}"
  docker build \
    --platform "linux/${arch/amd/amd64}" \
    -f docker/Dockerfile \
    -t "${image}" \
    .

  log "Pushing backend image: ${image}"
  docker push "${image}"

  echo "${image}"
}

build_and_push_frontend() {
  local arch="$1"
  local image="${FRONTEND_REPOSITORY}:${arch}_${TAG}"

  log "Building frontend image: ${image}"
  docker build \
    --platform "linux/${arch/amd/amd64}" \
    -f frontend/Dockerfile \
    -t "${image}" \
    .

  log "Pushing frontend image: ${image}"
  docker push "${image}"

  echo "${image}"
}

write_feishu_tag() {
  local sheet="$1"
  local component="$2"
  local tag="$3"

  if [[ ! -f "$FEISHU_CONFIG_FILE" ]]; then
    log "Feishu config not found at ${FEISHU_CONFIG_FILE}, skipping tag write"
    return 0
  fi

  local app_id app_secret
  app_id="$(python3 - "$FEISHU_CONFIG_FILE" "feishu_app_id" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
print(data.get("feishu_app_id", ""))
PY
)"
  app_secret="$(python3 - "$FEISHU_CONFIG_FILE" "feishu_app_secret" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
print(data.get("feishu_app_secret", ""))
PY
)"

  if [[ -z "$app_id" || -z "$app_secret" ]]; then
    log "Feishu credentials not found, skipping tag write"
    return 0
  fi

  local token
  token="$(curl --fail -sS -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
    -H "Content-Type: application/json" \
    -d "{\"app_id\":\"${app_id}\",\"app_secret\":\"${app_secret}\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["tenant_access_token"])')"

  log "Writing tag ${tag} to Feishu sheet ${sheet} for component ${component}"
  curl --fail -sS -X PUT \
    "https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/sheets/${sheet}/records" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    -d "{\"records\":[{\"fields\":{\"component\":\"${component}\",\"tag\":\"${tag}\"}}]}" \
    || log "Failed to write Feishu tag (non-fatal)"
}

main() {
  require_cmd docker

  parse_args "$@"

  # 当前纯正则阶段，所有 profile 共用同一个镜像
  # amd 和 amd-without-cuda 用同一个 AMD 镜像
  # arm 和 arm-without-cuda 用同一个 ARM 镜像
  # l4t 和 thor-spark 用同一个 ARM 镜像（未来 NER 阶段再分化）
  # 这样飞书表每个 sheet 都能找到对应的 tag

  if [[ -z "$COMPONENT" || "$COMPONENT" == "backend" ]]; then
    build_and_push_backend "amd"
    build_and_push_backend "arm"

    # AMD_with_cuda sheet: amd profile
    write_feishu_tag "AMD_with_cuda" "desensitize_backend" "amd_${TAG}"
    # AMD_with_cuda sheet: amd-without-cuda profile (same image, no runtime: nvidia)
    write_feishu_tag "AMD_with_cuda" "desensitize_backend_amd_without_cuda" "amd_${TAG}"
    # ARM_with_cuda sheet: arm profile
    write_feishu_tag "ARM_with_cuda" "desensitize_backend" "arm_${TAG}"
    # ARM_without_cuda sheet: arm-without-cuda profile
    write_feishu_tag "ARM_without_cuda" "desensitize_backend" "arm_${TAG}"
    # l4t sheet
    write_feishu_tag "l4t" "desensitize_backend" "arm_${TAG}"
    # thor_spark sheet
    write_feishu_tag "thor_spark" "desensitize_backend" "arm_${TAG}"
  fi

  if [[ -z "$COMPONENT" || "$COMPONENT" == "frontend" ]]; then
    build_and_push_frontend "amd"
    build_and_push_frontend "arm"

    write_feishu_tag "AMD_with_cuda" "desensitize_frontend" "amd_${TAG}"
    write_feishu_tag "AMD_with_cuda" "desensitize_frontend_amd_without_cuda" "amd_${TAG}"
    write_feishu_tag "ARM_with_cuda" "desensitize_frontend" "arm_${TAG}"
    write_feishu_tag "ARM_without_cuda" "desensitize_frontend" "arm_${TAG}"
    write_feishu_tag "l4t" "desensitize_frontend" "arm_${TAG}"
    write_feishu_tag "thor_spark" "desensitize_frontend" "arm_${TAG}"
  fi

  log "Done. Images tagged with ${TAG}"
}

main "$@"
