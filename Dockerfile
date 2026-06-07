# whatfirst-small — Gradio app + a local llama.cpp server, one container.
# Builds llama-server (multimodal) from source, then runs the Gradio UI in front
# of it. No cloud APIs at runtime.

FROM python:3.11-slim

# --- build llama.cpp (llama-server includes multimodal / mtmd support) -------
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp /opt/llama.cpp \
    && cmake -S /opt/llama.cpp -B /opt/llama.cpp/build \
        -DGGML_NATIVE=OFF -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF \
    && cmake --build /opt/llama.cpp/build --config Release -j --target llama-server \
    && rm -rf /opt/llama.cpp/.git

# --- non-root user (Hugging Face Spaces convention) --------------------------
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    MODEL_DIR=/home/user/models \
    MODEL_REPO=ggml-org/Qwen2.5-VL-3B-Instruct-GGUF \
    MODEL_FILE=Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf \
    MMPROJ_FILE=mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf \
    PORT=7860

WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY --chown=user . .

EXPOSE 7860
CMD ["bash", "start.sh"]
