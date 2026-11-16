#!/usr/bin/env bash
set -euo pipefail

base_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
xrmc_python="$base_dir/../venv/bin/python"
xrmc_bin="$base_dir/.deps/xrmc/bin/xrmc"
xraylib_dir="$base_dir/.deps/xraylib/usr/lib/x86_64-linux-gnu"
experiment_dir="$base_dir/minimo_pmmaa_furo"

if [[ ! -x "$xrmc_bin" ]]; then
  echo "XRMC local ausente: execute ./simulacao_xrmc/instalar_xrmc_local.sh" >&2
  exit 2
fi
if [[ ! -x "$xrmc_python" ]]; then
  echo "Python do ambiente do projeto ausente: $xrmc_python" >&2
  exit 2
fi
if [[ ! -f "$xraylib_dir/libxrl.so.11" ]]; then
  echo "xraylib local ausente: execute ./simulacao_xrmc/instalar_xrmc_local.sh" >&2
  exit 2
fi

mkdir -p "$experiment_dir/output"
(
  cd "$experiment_dir"
  LD_LIBRARY_PATH="$xraylib_dir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$xrmc_bin" input.dat
)
"$xrmc_python" "$base_dir/converter_imagem_xrmc.py" \
  "$experiment_dir/output/image.dat" "$experiment_dir/output/image.npy" \
  --largura 256 --altura 256 \
  --preview "$experiment_dir/output/image.png"
cp "$experiment_dir/manifest.json" "$experiment_dir/output/manifest.json"
"$xrmc_python" "$base_dir/validar_minimo.py" "$experiment_dir/output/image.npy"
