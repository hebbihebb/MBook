#!/usr/bin/env python3
"""Quick test script to generate audio with Chatterbox Turbo"""

import os
import sys
from datetime import datetime

# Test if chatterbox is available
try:
    from chatterbox_engine import ChatterboxTurboEngine, is_chatterbox_available
    import soundfile as sf
except ImportError as e:
    print(f"Error: Missing dependencies - {e}")
    print("Install with: pip install chatterbox-tts soundfile")
    sys.exit(1)

def main():
    # Check if Chatterbox is available
    if not is_chatterbox_available():
        print("Error: chatterbox-tts not installed")
        print("Install with: ./venv/bin/pip install chatterbox-tts")
        return 1

    # Sample text
    text = "Hello! This is a test of the Chatterbox Turbo text-to-speech engine. It uses voice cloning to match a reference speaker."

    # Use default male voice sample
    reference_audio = "voice_samples/en_us_male_warm.wav"

    if not os.path.exists(reference_audio):
        print(f"Error: Reference audio not found: {reference_audio}")
        print("Run: ./venv/bin/python generate_voice_samples.py")
        return 1

    print("=" * 60)
    print("Chatterbox Turbo Quick Test")
    print("=" * 60)
    print(f"\nText: {text}")
    print(f"Reference: {reference_audio}")
    print()

    # Initialize engine
    print("Loading Chatterbox Turbo engine...")
    engine = ChatterboxTurboEngine(device="cuda", reference_audio=reference_audio)
    engine.load()

    # Generate audio
    print("Generating audio...")
    audio = engine.generate_audio(text)

    # Save output
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"output/chatterbox_test_{timestamp}.wav"

    sf.write(output_path, audio, engine.sr)

    # Stats
    duration = len(audio) / engine.sr

    print("\n" + "=" * 60)
    print("Success!")
    print("=" * 60)
    print(f"Output: {output_path}")
    print(f"Duration: {duration:.1f} seconds")
    print(f"Sample rate: {engine.sr} Hz")
    print()

    # Cleanup
    engine.cleanup()

    return 0

if __name__ == "__main__":
    sys.exit(main())
