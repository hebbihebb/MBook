import os
import sys
import subprocess

LOCAL_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "maya1")
MODEL_ID = "maya-research/maya1"

def install_spacy_model():
    print("Downloading Spacy model 'en_core_web_sm'...")
    try:
        subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
        print("Spacy model installed.")
    except Exception as e:
        print(f"Error installing Spacy model: {e}")

def download_hf_model():
    print(f"Downloading HuggingFace model '{MODEL_ID}'...")
    try:
        from huggingface_hub import snapshot_download

        os.makedirs(LOCAL_MODEL_DIR, exist_ok=True)
        print(f"Downloading to local path: {LOCAL_MODEL_DIR}")
        try:
            snapshot_download(
                MODEL_ID,
                local_dir=LOCAL_MODEL_DIR,
                local_dir_use_symlinks=False
            )
        except TypeError:
            # Backward compatibility for older huggingface_hub versions.
            snapshot_download(MODEL_ID, local_dir=LOCAL_MODEL_DIR)
        print("HF Model downloaded successfully.")
    except Exception as e:
        print(f"Error downloading HF model (Do you have access/internet?): {e}")

def download_vad_model():
    print("Downloading Silero VAD model...")
    try:
        import torch
        # Triggers download to torch hub cache
        torch.hub.load(repo_or_dir='snakers4/silero-vad',
                       model='silero_vad',
                       force_reload=False,
                       onnx=False)
        print("Silero VAD model downloaded.")
    except Exception as e:
        print(f"Error downloading VAD model: {e}")

if __name__ == "__main__":
    print("Starting Model Setup...")
    install_spacy_model()
    download_vad_model()
    download_hf_model()
    print("Model setup complete.")
