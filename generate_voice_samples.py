#!/usr/bin/env python3
"""
Voice Sample Generator for Chatterbox Turbo

This script generates reference voice samples using edge-tts (Microsoft Edge TTS).
These samples are used for voice cloning with the Chatterbox Turbo TTS engine.

Requirements:
    pip install edge-tts soundfile

Usage:
    python generate_voice_samples.py
"""

import os
import sys
import asyncio


# Sample texts for voice generation (each ~10 seconds when spoken)
SAMPLE_TEXTS = {
    "male_us": (
        "The art of narration requires clarity, warmth, and authentic expression. "
        "A skilled narrator brings stories to life with nuanced emotion and precise "
        "diction, engaging listeners through every chapter."
    ),
    "female_us": (
        "Professional voice work demands attention to pacing, tone, and emotional range. "
        "Clear articulation and natural delivery are essential for engaging listeners "
        "and bringing characters to life with authenticity."
    ),
    "male_gb": (
        "The British broadcasting tradition emphasizes measured pacing, refined "
        "pronunciation, and authoritative delivery. This classic style remains "
        "the gold standard for professional narration and storytelling."
    )
}

# Edge-TTS voice mappings
VOICE_MAPPINGS = {
    "en_us_male_warm.wav": {
        "voice": "en-US-GuyNeural",
        "text": SAMPLE_TEXTS["male_us"],
        "description": "US Male (Warm baritone)"
    },
    "en_us_female_clear.wav": {
        "voice": "en-US-JennyNeural",
        "text": SAMPLE_TEXTS["female_us"],
        "description": "US Female (Clear articulation)"
    },
    "en_gb_male_standard.wav": {
        "voice": "en-GB-RyanNeural",
        "text": SAMPLE_TEXTS["male_gb"],
        "description": "UK Male (BBC style)"
    }
}


async def generate_sample(filename, config):
    """Generate a single voice sample using edge-tts."""
    import edge_tts

    output_path = os.path.join("voice_samples", filename)
    temp_path = output_path.replace(".wav", "_temp.mp3")

    print(f"Generating {filename}...")
    print(f"  Voice: {config['voice']}")
    print(f"  Description: {config['description']}")

    try:
        # Generate audio with edge-tts
        communicate = edge_tts.Communicate(config["text"], config["voice"])
        await communicate.save(temp_path)

        # Convert to 22.05kHz mono WAV
        if not convert_to_wav(temp_path, output_path):
            return False

        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)

        print(f"  ✓ Created {output_path}\n")
        return True

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def convert_to_wav(input_path, output_path):
    """Convert audio file to 22.05kHz mono WAV using ffmpeg or soundfile."""
    # Try ffmpeg first (best quality)
    try:
        import subprocess
        result = subprocess.run(
            [
                "ffmpeg",
                "-i", input_path,
                "-ar", "22050",  # 22.05kHz sample rate
                "-ac", "1",      # Mono
                "-y",            # Overwrite
                output_path
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return True

    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # Fall back to Python-based conversion

    # Fallback: Use Python libraries
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(input_path)
        audio = audio.set_frame_rate(22050)  # 22.05kHz
        audio = audio.set_channels(1)        # Mono
        audio.export(output_path, format="wav")
        return True

    except ImportError:
        print("  ⚠ ffmpeg not found and pydub not available")
        print("    Install: pip install pydub")
        print("    Or install ffmpeg: sudo apt-get install ffmpeg")
        return False
    except Exception as e:
        print(f"  ✗ Conversion error: {e}")
        return False


def verify_samples():
    """Verify generated samples meet requirements."""
    try:
        import soundfile as sf
    except ImportError:
        print("Note: Install soundfile to verify samples: pip install soundfile")
        return True

    print("\nVerifying samples...")
    all_valid = True

    for filename in VOICE_MAPPINGS.keys():
        filepath = os.path.join("voice_samples", filename)
        if not os.path.exists(filepath):
            continue

        try:
            data, samplerate = sf.read(filepath)
            duration = len(data) / samplerate
            channels = 1 if data.ndim == 1 else data.shape[1]

            status = "✓" if 8 <= duration <= 15 and samplerate == 22050 and channels == 1 else "⚠"
            print(f"  {status} {filename}:")
            print(f"      Duration: {duration:.1f}s")
            print(f"      Sample rate: {samplerate} Hz")
            print(f"      Channels: {channels}")

            if duration < 8:
                print(f"      Warning: Duration too short (< 8s)")
                all_valid = False
            if samplerate != 22050:
                print(f"      Warning: Sample rate not 22050 Hz")

        except Exception as e:
            print(f"  ✗ {filename}: Error reading file - {e}")
            all_valid = False

    return all_valid


async def main_async():
    """Generate all voice samples asynchronously."""
    print("=" * 60)
    print("Voice Sample Generator for Chatterbox Turbo")
    print("=" * 60)
    print()

    # Create voice_samples directory
    os.makedirs("voice_samples", exist_ok=True)

    # Check for edge-tts
    try:
        import edge_tts
    except ImportError:
        print("edge-tts not installed.")
        print("Installing: pip install edge-tts")
        print()
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "edge-tts"])
            print("✓ edge-tts installed\n")
        except subprocess.CalledProcessError:
            print("✗ Failed to install edge-tts")
            print("Manual installation: pip install edge-tts")
            return 1

    # Generate each sample
    success_count = 0
    for filename, config in VOICE_MAPPINGS.items():
        if await generate_sample(filename, config):
            success_count += 1

    # Verify samples
    verify_samples()

    # Summary
    print("\n" + "=" * 60)
    print(f"Generated {success_count}/{len(VOICE_MAPPINGS)} voice samples")
    print("=" * 60)

    if success_count == len(VOICE_MAPPINGS):
        print("\n✓ All samples generated successfully!")
        print("\nNext steps:")
        print("  1. Test samples with: python test_chatterbox_gui.py")
        print("  2. Replace with higher quality samples if needed")
        print("  3. See voice_samples/README.md for details")
        return 0
    else:
        print("\n⚠ Some samples failed to generate")
        print("  See voice_samples/README.md for alternative methods")
        return 1


def main():
    """Main entry point."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
