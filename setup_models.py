import os
import sys
import subprocess

def install_spacy_model():
    print("Downloading Spacy model 'en_core_web_sm'...")
    try:
        subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
        print("Spacy model installed.")
    except Exception as e:
        print(f"Error installing Spacy model: {e}")

def download_hf_model():
    print("Downloading HuggingFace model 'maya-research/maya1'...")
    try:
        from transformers import AutoTokenizer, AutoModel
        model_id = "maya-research/maya1"
        
        print(f"Downloading Tokenizer for {model_id}...")
        try:
            AutoTokenizer.from_pretrained(model_id)
        except:
             print("Tokenizer not found (might not use one), skipping.")

        print(f"Downloading Model for {model_id}...")
        AutoModel.from_pretrained(model_id)
        
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
