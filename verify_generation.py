import os
import sys
import torch
import numpy as np
from scipy.io import wavfile

# Ensure imports work
sys.path.append(os.getcwd())

# Monkeypatch audioop for pydub (needed for assembler, though we focus on pipeline generation here)
import audioop
sys.modules["audioop"] = audioop

from pipeline import Maya1Pipeline

from gtts import gTTS
import os

def generate_samples():
    print("Initializing Generation Test (using Pipeline class logic)...")
    pipeline = Maya1Pipeline()
    pipeline.load_model()
    
    # Create output dir
    os.makedirs("generated_samples", exist_ok=True)
    
    # Needs a reference audio?
    ref_audio = "reference_audio/test_ref.wav"
    
    test_cases = [
        ("Short", "Hello world."), 
        ("Medium", "This is a medium length sentence to test the generation capabilities of the model."),
        ("Long", "This is a much longer paragraph intended to stress test the model's ability to maintain coherence over a longer duration. It should theoretically produce a longer audio file corresponding to the text input provided here.")
    ]

    for name, text in test_cases:
        print(f"\nGenerating '{name}' sample...")
        print(f"Text: {text}")
        
        try:
            # Generate using Pipeline (which now handles fallback)
            audio_tensor = pipeline.generate_chunk(text, ref_audio)
            
            if audio_tensor is not None:
                # tensor shape [1, T] or [T]
                # Note: gTTS fallback returns float32 tensor
                audio_np = audio_tensor.squeeze().numpy()
                
                # Check consistency
                duration = len(audio_np) / 24000
                print(f" -> Generated {duration:.2f}s of audio.")
                
                out_path = f"generated_samples/sample_{name.lower()}.wav"
                wavfile.write(out_path, 24000, audio_np)
                print(f" -> Saved to {out_path}")
            else:
                print(" -> No output generated (None).")
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f" -> Error generating {name}: {e}")

if __name__ == "__main__":
    generate_samples()
