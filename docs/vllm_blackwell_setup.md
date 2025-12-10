# vLLM on RTX 5060 Ti (Blackwell) - Setup Guide

> **Note**: This guide was saved on 2024-12-10 as a reference for enabling fast batch inference on Blackwell GPUs (RTX 50 series) when lmdeploy doesn't support them yet.

## The Problem

Pre-built Python packages like `lmdeploy` and `vLLM` don't include CUDA kernels compiled for Blackwell GPUs (Compute Capability 12.0 / sm_120). The solution is to build from source inside a Docker container with the correct CUDA toolkit.

---

## Prerequisites

- Docker installed
- NVIDIA GPU driver installed (should already be working if `nvidia-smi` works)
- RTX 50 series GPU (5060 Ti, 5070, 5080, 5090, etc.)

---

## Step 1: Install NVIDIA Container Toolkit

Run this once to allow Docker to see your GPU:

```bash
# 1. Configure the repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 2. Update and Install
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 3. Configure Docker and Restart
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

---

## Step 2: Create the "Blackwell-Ready" Dockerfile

Save this as `Dockerfile` in an empty folder:

```dockerfile
# Base image: Official NVIDIA CUDA 12.8 Development environment (Required for sm_120)
FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu22.04

# Set environment variables to non-interactive (prevents installation freezes)
ENV DEBIAN_FRONTEND=noninteractive

# 1. Install System Dependencies
# python3.11 is recommended for stability with vLLM
RUN apt-get update && apt-get install -y \
    python3.11 python3-pip git ninja-build libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Install PyTorch Nightly (Crucial for Blackwell Support)
# We use the specific index for CUDA 12.8
RUN pip3 install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128

# 3. Set Architecture Flags for RTX 50-Series
# "12.0" is the specific Compute Capability for Blackwell Consumer cards
ENV TORCH_CUDA_ARCH_LIST="12.0"
# Force Flash Attention 2 (FA3 is not yet stable on Blackwell)
ENV VLLM_FLASH_ATTN_VERSION="2"

# 4. Compile vLLM from Source
# We clone the main branch to get the latest patches
WORKDIR /app
RUN git clone https://github.com/vllm-project/vllm.git \
    && cd vllm \
    && pip3 install -e .

# 5. Set the entrypoint
ENTRYPOINT ["python3", "-m", "vllm.entrypoints.openai.api_server"]
```

---

## Step 3: Build and Run

Run these commands inside the folder where you saved the Dockerfile:

### 1. Build the Image (~15-20 mins)

```bash
docker build -t vllm-blackwell .
```

### 2. Run the Container

Replace `your-model-name` with the actual path or HuggingFace ID:

```bash
docker run --gpus all \
    -p 8000:8000 \
    --ipc=host \
    vllm-blackwell \
    --model "maya-research/maya1"
```

---

## Verification

To confirm it's working, open a new terminal and send a test request:

```bash
curl http://localhost:8000/v1/models
```

If you see a JSON response with your model name, your RTX 5060 Ti is officially serving traffic!

---

## Using with Maya1 Audiobook Converter

Once vLLM is running as a server, you would need to modify `fast_maya_engine.py` to use the OpenAI-compatible API instead of lmdeploy. The vLLM server exposes an OpenAI-compatible endpoint at `http://localhost:8000/v1/`.

### Future Integration Steps

1. Create a new engine class `VLLMMaya1Engine` 
2. Use the `openai` Python library to send requests to the local vLLM server
3. Handle SNAC token extraction from the response
4. Integrate with the existing batch processing flow

---

## Relevant Links

- [vLLM GitHub](https://github.com/vllm-project/vllm)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
- [PyTorch Nightly Builds](https://pytorch.org/get-started/locally/)
