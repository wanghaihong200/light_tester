#!/usr/bin/env bash
# 计划 12:SoloPi Harness CLI 安装(幂等)。
# 事实(docs/superpowers/research/2026-09-07-plan12-solopi-prereq.md):PyPI 无此包,
# 唯一渠道 = alipay/SoloPi Harness 分支源码目录 pip install -e;Windows 用 python -m 调用。
# 用法:cd backend && source .venv/Scripts/activate && bash scripts/setup-solopi.sh
set -euo pipefail
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOLOPI_DIR="${SOLOPI_DIR:-$BACKEND_DIR/../../SoloPi}"   # 默认仓外同级目录(d:\...\wang_tester_club\SoloPi),不进 monorepo
if [ ! -d "$SOLOPI_DIR/.git" ]; then
  git clone --depth 1 -b Harness https://github.com/alipay/SoloPi.git "$SOLOPI_DIR"
fi
python -m pip install -e "$SOLOPI_DIR/solopi-harness-cli"
python - <<'PY'
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec("solopi_harness") else 1)
PY
echo "== solopi_harness 安装 OK =="
python -m solopi_harness.solopi_ai --pretty doctor || echo "!! doctor 未通过:先接设备/装 App(见计划 12 Task 1 Step 3)"
