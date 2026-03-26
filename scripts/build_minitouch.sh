#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MINITOUCH_REPO_URL="${MINITOUCH_REPO_URL:-https://github.com/openstf/minitouch.git}"
MINITOUCH_REF="${MINITOUCH_REF:-master}"
MINITOUCH_WORK_ROOT="${MINITOUCH_WORK_ROOT:-${RUNNER_TEMP:-${REPO_ROOT}/.cache}/minitouch-build}"
MINITOUCH_SOURCE_DIR="${MINITOUCH_SOURCE_DIR:-${MINITOUCH_WORK_ROOT}/src}"
MINITOUCH_OUTPUT_DIR="${MINITOUCH_OUTPUT_DIR:-${REPO_ROOT}/out/minitouch-package}"
MINITOUCH_APP_ABI="${MINITOUCH_APP_ABI:-}"

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

detect_ndk_build() {
  local candidates=(
    "${NDK_BUILD:-}"
    "${ANDROID_NDK_HOME:-}/ndk-build"
    "${ANDROID_NDK_ROOT:-}/ndk-build"
    "${ANDROID_NDK:-}/ndk-build"
  )

  if command -v ndk-build >/dev/null 2>&1; then
    candidates+=("$(command -v ndk-build)")
  fi

  for candidate in "${candidates[@]}"; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  return 1
}

NDK_BUILD_BIN="$(detect_ndk_build || true)"
if [[ -z "${NDK_BUILD_BIN}" ]]; then
  echo "ndk-build not found. Set NDK_BUILD or ANDROID_NDK_HOME before running." >&2
  exit 1
fi

echo "Using ndk-build: ${NDK_BUILD_BIN}"
echo "Cloning ${MINITOUCH_REPO_URL} (${MINITOUCH_REF})"

rm -rf "${MINITOUCH_SOURCE_DIR}" "${MINITOUCH_OUTPUT_DIR}"
mkdir -p "${MINITOUCH_WORK_ROOT}" "${MINITOUCH_OUTPUT_DIR}"

git clone --depth 1 --branch "${MINITOUCH_REF}" "${MINITOUCH_REPO_URL}" "${MINITOUCH_SOURCE_DIR}"
git -C "${MINITOUCH_SOURCE_DIR}" submodule update --init --depth 1
SOURCE_COMMIT="$(git -C "${MINITOUCH_SOURCE_DIR}" rev-parse HEAD)"

build_args=()
if [[ -n "${MINITOUCH_APP_ABI}" ]]; then
  build_args+=("APP_ABI=${MINITOUCH_APP_ABI}")
fi

"${NDK_BUILD_BIN}" -C "${MINITOUCH_SOURCE_DIR}" "${build_args[@]}"

PACKAGE_ROOT="${MINITOUCH_OUTPUT_DIR}/bin/minitouch"
LIBS_ROOT="${PACKAGE_ROOT}/libs"
mkdir -p "${LIBS_ROOT}"

copied_any=0
for abi_dir in "${MINITOUCH_SOURCE_DIR}"/libs/*; do
  if [[ ! -d "${abi_dir}" ]]; then
    continue
  fi

  abi="$(basename "${abi_dir}")"
  target_dir="${LIBS_ROOT}/${abi}"
  mkdir -p "${target_dir}"

  copied_this_abi=0
  for binary_name in minitouch minitouch-nopie; do
    source_file="${abi_dir}/${binary_name}"
    if [[ -f "${source_file}" ]]; then
      install -m 0755 "${source_file}" "${target_dir}/${binary_name}"
      copied_any=1
      copied_this_abi=1
    fi
  done

  if [[ "${copied_this_abi}" -eq 0 ]]; then
    rmdir "${target_dir}"
  fi
done

if [[ "${copied_any}" -eq 0 ]]; then
  echo "No minitouch binaries were produced under ${MINITOUCH_SOURCE_DIR}/libs" >&2
  exit 1
fi

if [[ -f "${REPO_ROOT}/bin/minitouch/README.md" ]]; then
  install -m 0644 "${REPO_ROOT}/bin/minitouch/README.md" "${PACKAGE_ROOT}/README.md"
fi
copy_upstream_notice_files "${MINITOUCH_SOURCE_DIR}" "${PACKAGE_ROOT}"

cat > "${PACKAGE_ROOT}/build-info.txt" <<EOF
source_repo=${MINITOUCH_REPO_URL}
source_ref=${MINITOUCH_REF}
source_commit=${SOURCE_COMMIT}
ndk_build=${NDK_BUILD_BIN}
built_at_utc=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF

echo "Packaged files:"
find "${MINITOUCH_OUTPUT_DIR}" -type f | sort
