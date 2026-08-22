#!/usr/bin/env bash
# Resolve one Tide coordinate for HEAD and synchronize package metadata.
# Author: Silan Hu <silan.hu@u.nus.edu>
# Copyright 2024-2026 Silan Hu

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPDATE_SCRIPT="${ROOT_DIR}/scripts/update-project-version.sh"
DRY_RUN=0
EXPLICIT_VERSION=""

usage() {
  echo "usage: $0 [--dry-run] [VERSION]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    -*)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "${EXPLICIT_VERSION}" ]]; then
        echo "error: only one version may be supplied" >&2
        exit 2
      fi
      EXPLICIT_VERSION="$1"
      shift
      ;;
  esac
done

WORKTREE_STATUS="$(git -C "${ROOT_DIR}" status --porcelain --untracked-files=normal)"
if [[ ${DRY_RUN} -eq 0 && -n "${WORKTREE_STATUS}" ]]; then
  echo "error: commit or stash tracked changes before resolving a Tide version" >&2
  echo "       the coordinate must identify one immutable functional HEAD" >&2
  exit 1
fi

if [[ -n "${EXPLICIT_VERSION}" ]]; then
  NEW_VERSION="${EXPLICIT_VERSION}"
else
  command -v tide >/dev/null 2>&1 || {
    echo "error: tide is not installed; install Tide or pass VERSION explicitly" >&2
    exit 1
  }

  RELEASE_COUNT="$(tide release list --local-only | awk 'END { print NR + 0 }')"
  if [[ "${RELEASE_COUNT}" -lt 2 ]]; then
    echo "error: EasyRemote requires its two annotated Tide bootstrap anchors" >&2
    echo "       fetch them with: git fetch origin 'refs/tags/*:refs/tags/*'" >&2
    exit 1
  fi
  NEW_VERSION="$(tide mark --local-only)"
fi

if ! [[ "${NEW_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([ab][0-9]+|rc[0-9]+)?([.+-][0-9A-Za-z-]+)*$ ]]; then
  echo "error: invalid Tide/PEP 440 version: ${NEW_VERSION}" >&2
  exit 1
fi

OLD_VERSION="$(python3 -c 'import pathlib,sys; namespace={}; exec((pathlib.Path(sys.argv[1]) / "easyremote/_version.py").read_text(), namespace); print(namespace["__version__"])' "${ROOT_DIR}" 2>/dev/null || true)"
echo "Old version : ${OLD_VERSION:-<unavailable>}"
echo "Tide version: ${NEW_VERSION}"

if [[ ${DRY_RUN} -eq 1 ]]; then
  if "${UPDATE_SCRIPT}" --check "${NEW_VERSION}" >/dev/null 2>&1; then
    echo "Project is already aligned; no files were changed."
  else
    echo "Project would be synchronized; no files were changed."
  fi
  exit 0
fi

"${UPDATE_SCRIPT}" "${NEW_VERSION}"
