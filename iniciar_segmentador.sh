#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python_bin="$project_dir/venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  echo "Ambiente ausente: crie venv/ e instale requirements.txt em $project_dir" >&2
  exit 2
fi
cd "$project_dir"
exec "$python_bin" interface.py
