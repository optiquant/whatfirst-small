"""Fetch the GGUF weights + vision projector from the Hub into MODEL_DIR.

Run once at container start (idempotent — hf_hub_download skips files already
present). Kept tiny and dependency-light so the container can pull the model
before the server boots.
"""

import os

from huggingface_hub import hf_hub_download

REPO = os.environ.get("MODEL_REPO", "ggml-org/Qwen2.5-VL-3B-Instruct-GGUF")
MODEL_FILE = os.environ.get("MODEL_FILE", "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf")
MMPROJ_FILE = os.environ.get("MMPROJ_FILE", "mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf")
MODEL_DIR = os.environ.get("MODEL_DIR", "/models")


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    for fname in (MODEL_FILE, MMPROJ_FILE):
        print(f"[download] {REPO}/{fname} -> {MODEL_DIR}", flush=True)
        hf_hub_download(repo_id=REPO, filename=fname, local_dir=MODEL_DIR)
    print("[download] done", flush=True)


if __name__ == "__main__":
    main()
