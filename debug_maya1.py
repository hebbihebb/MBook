import os
import sys
# Set explicit cache dir if needed, but default is usually ~/.cache/huggingface/hub
from transformers import AutoConfig, AutoModel

def inspect_model():
    model_id = "maya-research/maya1"
    print(f"Inspecting {model_id}...")
    
    try:
        config = AutoConfig.from_pretrained(model_id)
        print("Config loaded successfully.")
        print(f"Architecture: {config.architectures}")
        print(f"Model Type: {config.model_type}")
        print(f"Task specific params: {config.to_dict()}")
        
        # Try loading model to confirm weights exist
        model = AutoModel.from_pretrained(model_id)
        print("Model weights loaded successfully.")
        return config
    except Exception as e:
        print(f"Error inspecting model: {e}")

if __name__ == "__main__":
    inspect_model()
