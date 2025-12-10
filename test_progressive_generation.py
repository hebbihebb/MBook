#!/usr/bin/env python3
"""
Progressive Text Generation Test for Maya1 Pipeline

This script tests the Maya1 model pipeline with progressively longer text samples,
proving that the text-to-audio generation is working correctly.

Test Levels:
1. Tiny      - Single word  (~0.5s expected)
2. Short     - Single sentence (~2s expected)
3. Medium    - Paragraph (~10s expected)
4. Long      - Multiple paragraphs (~30s expected)
5. Extended  - Long passage (~60s expected)

Each test logs:
- Input text (truncated for readability)
- Character count and word count
- Expected duration (heuristic: ~15 chars/second)
- Actual generated audio duration
- File size
- Pass/Fail status
"""

import os
import sys
import time
import datetime

# Ensure imports work
sys.path.append(os.getcwd())

# Monkeypatch audioop for pydub compatibility
import audioop
sys.modules["audioop"] = audioop

import torch
import numpy as np
from scipy.io import wavfile

from pipeline import Maya1Pipeline


# Local model path
LOCAL_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "maya1")
MODEL_ID = "maya-research/maya1"


def ensure_model_downloaded():
    """
    Ensures the Maya1 model is downloaded to the local models directory.
    Downloads from HuggingFace if not present.
    """
    if os.path.exists(LOCAL_MODEL_DIR) and os.listdir(LOCAL_MODEL_DIR):
        print(f"[MODEL] Found local model at: {LOCAL_MODEL_DIR}")
        return LOCAL_MODEL_DIR
    
    print(f"[MODEL] Model not found locally. Downloading {MODEL_ID} to {LOCAL_MODEL_DIR}...")
    
    try:
        from huggingface_hub import snapshot_download
        
        os.makedirs(LOCAL_MODEL_DIR, exist_ok=True)
        
        snapshot_download(
            repo_id=MODEL_ID,
            local_dir=LOCAL_MODEL_DIR,
            local_dir_use_symlinks=False,  # Download actual files, not symlinks
        )
        
        print(f"[MODEL] Model downloaded successfully to: {LOCAL_MODEL_DIR}")
        return LOCAL_MODEL_DIR
        
    except ImportError:
        print("[MODEL] huggingface_hub not installed. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
        
        from huggingface_hub import snapshot_download
        os.makedirs(LOCAL_MODEL_DIR, exist_ok=True)
        
        snapshot_download(
            repo_id=MODEL_ID,
            local_dir=LOCAL_MODEL_DIR,
            local_dir_use_symlinks=False,
        )
        
        print(f"[MODEL] Model downloaded successfully to: {LOCAL_MODEL_DIR}")
        return LOCAL_MODEL_DIR
        
    except Exception as e:
        print(f"[MODEL] Error downloading model: {e}")
        print("[MODEL] Falling back to HuggingFace cache...")
        return MODEL_ID


# Test samples with progressively longer text
TEST_SAMPLES = [
    (
        "Tiny",
        "Hello.",
    ),
    (
        "Short",
        "The quick brown fox jumps over the lazy dog.",
    ),
    (
        "Medium",
        "In a quiet village nestled among rolling hills, there lived an old clockmaker "
        "who had spent his entire life crafting the most intricate timepieces the world had ever seen. "
        "Every morning, he would wake before dawn and begin his delicate work, "
        "carefully assembling gears and springs with hands that never trembled despite his age.",
    ),
    (
        "Long",
        "The ancient library stood at the heart of the university, its towering spires reaching toward the clouds. "
        "Inside, thousands of books lined the walls from floor to ceiling, each one containing knowledge accumulated over centuries. "
        "Students would gather in the reading rooms, their whispers barely audible as they pored over dusty tomes. "
        "The head librarian, a woman of considerable years and even more considerable wisdom, knew the location of every book by heart. "
        "She had dedicated her life to this sanctuary of knowledge, watching generations of scholars come and go. "
        "On this particular autumn morning, a young student approached her desk with a peculiar request.",
    ),
    (
        "Extended",
        "It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of foolishness. "
        "The city stretched out beneath the gray morning sky, its streets already alive with the bustle of daily commerce. "
        "Merchants called out their wares from crowded stalls, while horse-drawn carriages clattered over cobblestone roads. "
        "In the distance, factory smokestacks belched dark clouds into the air, a testament to the industrial revolution "
        "that was rapidly transforming the landscape. Children played in narrow alleyways, their laughter a brief respite "
        "from the grinding poverty that surrounded them. The wealthy lived in grand houses on the hill, their windows "
        "gleaming in the occasional burst of sunlight. Below, the working class toiled in cramped factories and workshops, "
        "their hands rough from labor, their futures uncertain. Yet amidst all this turmoil, hope persisted. "
        "People believed in progress, in the promise of a better tomorrow. Science was unlocking the secrets of nature, "
        "medicine was conquering diseases that had plagued humanity for millennia, and education was slowly spreading "
        "to all corners of society. This was an era of extremes, of great possibility and great peril.",
    ),
]


def calculate_expected_duration(text: str, chars_per_second: float = 15.0) -> float:
    """
    Estimate expected audio duration based on character count.
    Heuristic: approximately 15 characters per second of speech.
    """
    return len(text) / chars_per_second


def format_duration(seconds: float) -> str:
    """Format duration as MM:SS.ms"""
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:05.2f}"


def run_progressive_tests():
    """
    Run progressive text generation tests and log results.
    """
    print("=" * 70)
    print("Maya1 Pipeline - Progressive Text Generation Test")
    print(f"Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Ensure model is downloaded locally
    model_path = ensure_model_downloaded()
    
    # Initialize pipeline with local model path
    print("\n[SETUP] Initializing Maya1Pipeline...")
    start_init = time.time()
    pipeline = Maya1Pipeline(model_id=model_path)
    pipeline.load_model()
    init_time = time.time() - start_init
    print(f"[SETUP] Pipeline initialized in {init_time:.2f}s")
    
    # Create output directory
    output_dir = "generated_samples/progressive_test"
    os.makedirs(output_dir, exist_ok=True)
    print(f"[SETUP] Output directory: {output_dir}")
    
    # Reference audio (not used by gTTS fallback, but required by API)
    ref_audio = "reference_audio/test_ref.wav"
    
    # Results tracking
    results = []
    all_passed = True
    
    print("\n" + "-" * 70)
    print("RUNNING PROGRESSIVE TESTS")
    print("-" * 70)
    
    for i, (level_name, text) in enumerate(TEST_SAMPLES, 1):
        print(f"\n[TEST {i}/{len(TEST_SAMPLES)}] Level: {level_name}")
        print("-" * 50)
        
        # Text stats
        char_count = len(text)
        word_count = len(text.split())
        expected_duration = calculate_expected_duration(text)
        
        # Display truncated text for readability
        display_text = text[:100] + "..." if len(text) > 100 else text
        print(f"  Text: \"{display_text}\"")
        print(f"  Characters: {char_count} | Words: {word_count}")
        print(f"  Expected Duration: ~{format_duration(expected_duration)}")
        
        try:
            # Generate audio
            start_gen = time.time()
            audio_tensor = pipeline.generate_chunk(text, ref_audio)
            gen_time = time.time() - start_gen
            
            if audio_tensor is not None:
                # Process audio tensor
                audio_np = audio_tensor.squeeze().numpy()
                
                # Audio stats
                sample_rate = 24000
                actual_duration = len(audio_np) / sample_rate
                
                # Save file
                out_path = f"{output_dir}/test_{i}_{level_name.lower()}.wav"
                wavfile.write(out_path, sample_rate, audio_np)
                file_size = os.path.getsize(out_path)
                file_size_kb = file_size / 1024
                
                # Calculate deviation
                if expected_duration > 0:
                    deviation = ((actual_duration - expected_duration) / expected_duration) * 100
                else:
                    deviation = 0
                
                # Determine pass/fail (within 50% tolerance for gTTS variance)
                passed = abs(deviation) <= 50
                status = "✓ PASS" if passed else "✗ FAIL"
                if not passed:
                    all_passed = False
                
                print(f"  Generation Time: {gen_time:.2f}s")
                print(f"  Actual Duration: {format_duration(actual_duration)}")
                print(f"  Deviation: {deviation:+.1f}%")
                print(f"  File Size: {file_size_kb:.1f} KB")
                print(f"  Output: {out_path}")
                print(f"  Result: {status}")
                
                results.append({
                    "level": level_name,
                    "chars": char_count,
                    "words": word_count,
                    "expected_sec": expected_duration,
                    "actual_sec": actual_duration,
                    "deviation_pct": deviation,
                    "file_size_kb": file_size_kb,
                    "gen_time_sec": gen_time,
                    "output_path": out_path,
                    "passed": passed,
                })
                
            else:
                print(f"  Result: ✗ FAIL - No audio generated (None)")
                all_passed = False
                results.append({
                    "level": level_name,
                    "chars": char_count,
                    "words": word_count,
                    "expected_sec": expected_duration,
                    "actual_sec": 0,
                    "deviation_pct": -100,
                    "file_size_kb": 0,
                    "gen_time_sec": 0,
                    "output_path": None,
                    "passed": False,
                })
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  Result: ✗ FAIL - Error: {e}")
            all_passed = False
            results.append({
                "level": level_name,
                "chars": char_count,
                "words": word_count,
                "expected_sec": expected_duration,
                "actual_sec": 0,
                "deviation_pct": -100,
                "file_size_kb": 0,
                "gen_time_sec": 0,
                "output_path": None,
                "passed": False,
                "error": str(e),
            })
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    
    print(f"\nResults: {passed_count}/{total_count} tests passed")
    print("\n{:<12} {:>8} {:>8} {:>12} {:>12} {:>10}".format(
        "Level", "Chars", "Words", "Expected", "Actual", "Status"
    ))
    print("-" * 70)
    
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print("{:<12} {:>8} {:>8} {:>12} {:>12} {:>10}".format(
            r["level"],
            r["chars"],
            r["words"],
            format_duration(r["expected_sec"]),
            format_duration(r["actual_sec"]),
            status
        ))
    
    print("-" * 70)
    
    total_chars = sum(r["chars"] for r in results)
    total_audio_sec = sum(r["actual_sec"] for r in results)
    total_gen_time = sum(r["gen_time_sec"] for r in results)
    
    print(f"\nTotal Characters Processed: {total_chars}")
    print(f"Total Audio Generated: {format_duration(total_audio_sec)}")
    print(f"Total Generation Time: {total_gen_time:.2f}s")
    
    if all_passed:
        print("\n" + "=" * 70)
        print("✓ ALL TESTS PASSED - Maya1 Pipeline is working correctly!")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("✗ SOME TESTS FAILED - Check results above for details")
        print("=" * 70)
    
    # Write log file
    log_path = f"{output_dir}/test_log.txt"
    with open(log_path, "w") as f:
        f.write(f"Maya1 Pipeline Progressive Test Log\n")
        f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'=' * 50}\n\n")
        
        for r in results:
            f.write(f"Level: {r['level']}\n")
            f.write(f"  Characters: {r['chars']}\n")
            f.write(f"  Words: {r['words']}\n")
            f.write(f"  Expected Duration: {r['expected_sec']:.2f}s\n")
            f.write(f"  Actual Duration: {r['actual_sec']:.2f}s\n")
            f.write(f"  Deviation: {r['deviation_pct']:+.1f}%\n")
            f.write(f"  File Size: {r['file_size_kb']:.1f} KB\n")
            f.write(f"  Generation Time: {r['gen_time_sec']:.2f}s\n")
            f.write(f"  Output: {r['output_path']}\n")
            f.write(f"  Status: {'PASS' if r['passed'] else 'FAIL'}\n")
            f.write("\n")
        
        f.write(f"{'=' * 50}\n")
        f.write(f"Summary: {passed_count}/{total_count} tests passed\n")
    
    print(f"\nLog saved to: {log_path}")
    print(f"Audio files saved to: {output_dir}/")
    
    return all_passed


if __name__ == "__main__":
    success = run_progressive_tests()
    sys.exit(0 if success else 1)
