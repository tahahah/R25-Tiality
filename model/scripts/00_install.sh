#!/usr/bin/env bash
set -euo pipefail

# Detect project root (one level above this script)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but not found. Install from: https://github.com/astral-sh/uv" >&2
  exit 1
fi

(
  cd "$ROOT_DIR"
  echo "[1/3] Creating virtual environment (.venv) with uv..."
  uv venv

  echo "[2/3] Activating .venv..."
  # shellcheck disable=SC1091
  source .venv/bin/activate

  echo "[3/3] Installing Python dependencies from requirements.txt..."
  uv pip install -r requirements.txt

  echo "Optional: Attempting Hugging Face login if HF_TOKEN is present in .env..."
  python - <<'PY'
import os
from pathlib import Path
try:
    from dotenv import load_dotenv
except Exception:
    print("python-dotenv not installed yet or import failed; skipping HF login step.")
else:
    dotenv_path = Path(".env")
    if dotenv_path.exists():
        try:
            load_dotenv(dotenv_path=str(dotenv_path))
        except Exception as e:
            print(f"Failed to load .env: {e}")
    tok = os.getenv("HF_TOKEN")
    if tok:
        try:
            from huggingface_hub import login
            login(token=tok)
            print("HF login ok.")
        except Exception as e:
            print(f"HF login skipped due to error: {e}")
    else:
        print("HF_TOKEN not set in .env; skipping HF login.")
PY

  echo "Setup complete. To use:"
  echo "  source .venv/bin/activate"
)
