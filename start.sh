#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/models}"
MODEL_FILE="${MODEL_FILE:-Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf}"
MMPROJ_FILE="${MMPROJ_FILE:-mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf}"

# 1. Pull weights (idempotent).
python download_model.py

# 2. Launch the llama.cpp server (multimodal) on localhost in the background.
echo "[start] launching llama-server"
/opt/llama.cpp/build/bin/llama-server \
  --model "${MODEL_DIR}/${MODEL_FILE}" \
  --mmproj "${MODEL_DIR}/${MMPROJ_FILE}" \
  --host 127.0.0.1 --port 8080 \
  --ctx-size 8192 \
  --threads "$(nproc)" &

# 3. Start the Gradio app (foreground). is_ready() polls the server's /health,
#    so the UI comes up immediately and the button waits for the model.
echo "[start] launching gradio"
exec python app.py
