#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MAATOUCH_REPO_URL="${MAATOUCH_REPO_URL:-https://github.com/MaaAssistantArknights/MaaTouch.git}"
MAATOUCH_REF="${MAATOUCH_REF:-master}"
MAATOUCH_WORK_ROOT="${MAATOUCH_WORK_ROOT:-${RUNNER_TEMP:-${REPO_ROOT}/.cache}/maatouch-build}"
MAATOUCH_SOURCE_DIR="${MAATOUCH_SOURCE_DIR:-${MAATOUCH_WORK_ROOT}/src}"
MAATOUCH_OUTPUT_DIR="${MAATOUCH_OUTPUT_DIR:-${REPO_ROOT}/out/maatouch-package}"
MAATOUCH_APK_PATH="${MAATOUCH_SOURCE_DIR}/app/build/outputs/apk/release/app-release-unsigned.apk"

copy_upstream_notice_files() {
  local source_root="$1"
  local package_root="$2"
  local copied_any=0

  shopt -s nullglob
  local notice_files=("${source_root}"/LICENSE* "${source_root}"/NOTICE*)
  shopt -u nullglob

  for source_file in "${notice_files[@]}"; do
    if [[ -f "${source_file}" ]]; then
      install -m 0644 "${source_file}" "${package_root}/$(basename "${source_file}")"
      copied_any=1
    fi
  done

  if [[ "${copied_any}" -eq 0 ]]; then
    echo "Warning: no upstream LICENSE/NOTICE files found under ${source_root}" >&2
  fi
}

echo "Cloning ${MAATOUCH_REPO_URL} (${MAATOUCH_REF})"

rm -rf "${MAATOUCH_SOURCE_DIR}" "${MAATOUCH_OUTPUT_DIR}"
mkdir -p "${MAATOUCH_WORK_ROOT}" "${MAATOUCH_OUTPUT_DIR}"

git clone --depth 1 --branch "${MAATOUCH_REF}" "${MAATOUCH_REPO_URL}" "${MAATOUCH_SOURCE_DIR}"
SOURCE_COMMIT="$(git -C "${MAATOUCH_SOURCE_DIR}" rev-parse HEAD)"

chmod +x "${MAATOUCH_SOURCE_DIR}/gradlew"
"${MAATOUCH_SOURCE_DIR}/gradlew" -p "${MAATOUCH_SOURCE_DIR}" build

if [[ ! -f "${MAATOUCH_APK_PATH}" ]]; then
  echo "MaaTouch APK not found at ${MAATOUCH_APK_PATH}" >&2
  exit 1
fi

PACKAGE_ROOT="${MAATOUCH_OUTPUT_DIR}/bin/maatouch"
mkdir -p "${PACKAGE_ROOT}"
install -m 0644 "${MAATOUCH_APK_PATH}" "${PACKAGE_ROOT}/maatouch"
copy_upstream_notice_files "${MAATOUCH_SOURCE_DIR}" "${PACKAGE_ROOT}"

if [[ -f "${REPO_ROOT}/bin/maatouch/README.md" ]]; then
  install -m 0644 "${REPO_ROOT}/bin/maatouch/README.md" "${PACKAGE_ROOT}/README.md"
fi

cat > "${PACKAGE_ROOT}/build-info.txt" <<EOF
source_repo=${MAATOUCH_REPO_URL}
source_ref=${MAATOUCH_REF}
source_commit=${SOURCE_COMMIT}
apk_path=${MAATOUCH_APK_PATH}
built_at_utc=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF

echo "Packaged files:"
find "${MAATOUCH_OUTPUT_DIR}" -type f | sort
