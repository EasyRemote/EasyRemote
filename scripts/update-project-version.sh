#!/usr/bin/env bash
# Synchronize every committed EasyRemote package-version projection.
# Author: Silan Hu <silan.hu@u.nus.edu>
# Copyright 2024-2026 Silan Hu

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "${ROOT_DIR}/scripts/_version_sync.py" "$@"
