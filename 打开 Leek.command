#!/bin/bash
set -eu
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
choices=("${LEEK_PYTHON:-}" "$(command -v python3 || true)" "$HOME"/.local/share/uv/python/cpython-3.*/bin/python3)
for py in "${choices[@]}"; do
  if [ -x "$py" ] && "$py" -c 'import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    if [ -f .workbench-config.json ]; then set -- --config .workbench-config.json "$@"; fi
    exec "$py" -m research.workbench.app "$@"
  fi
done
printf 'Leek 需要已有的 Python 3.10 或更高版本。未安装任何软件。可设置 LEEK_PYTHON 指向本机解释器。\n'
read -r -p '按回车关闭…' _
exit 1
