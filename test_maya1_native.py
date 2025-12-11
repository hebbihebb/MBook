#!/usr/bin/env python3
"""
Progressive Text Generation Test for Maya1 Pipeline - Native Maya1 TTS

This script tests the ACTUAL Maya1 model for text-to-speech generation
using SNAC neural codec (NOT gTTS fallback).

Maya1 is a 3B-parameter TTS model that generates SNAC audio tokens
which are then decoded to 24kHz audio.

Test Levels:
1. Tiny      - Single word  (~0.5s expected)
2. Short     - Single sentence (~2s expected)
3. Medium    - Paragraph (~10s expected)
4. Long      - Multiple paragraphs (~30s expected)
5. Extended  - Long passage (~60s expected)
"""

import os
import sys
import time
import datetime

# Ensure imports work
sys.path.append(os.getcwd())

import torch
import numpy as np
import soundfile as sf

# Maya1 Token Constants (from official README)
CODE_START_TOKEN_ID = 128257
CODE_END_TOKEN_ID = 128258
CODE_TOKEN_OFFSET = 128266
SNAC_MIN_ID = 128266
SNAC_MAX_ID = 156937
SNAC_TOKENS_PER_FRAME = 7

SOH_ID = 128259
EOH_ID = 128260
SOA_ID = 128261
BOS_ID = 128000
TEXT_EOT_ID = 128009

# Local model path
LOCAL_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "maya1")
MODEL_ID = "maya-research/maya1"
SNAC_MODEL_ID = "hubertsiuzdak/snac_24khz"


def ensure_model_downloaded():
    """
    Ensures the Maya1 model is downloaded to the local models directory.
    """
    if os.path.exists(LOCAL_MODEL_DIR) and len(os.listdir(LOCAL_MODEL_DIR)) > 5:
        print(f"[MODEL] Found local model at: {LOCAL_MODEL_DIR}")
        return LOCAL_MODEL_DIR
    
    print(f"[MODEL] Model not found locally. Downloading {MODEL_ID} to {LOCAL_MODEL_DIR}...")
    
    try:
        from huggingface_hub import snapshot_download
        
        os.makedirs(LOCAL_MODEL_DIR, exist_ok=True)
        
        snapshot_download(
            repo_id=MODEL_ID,
            local_dir=LOCAL_MODEL_DIR,
        )
        
        print(f"[MODEL] Model downloaded successfully to: {LOCAL_MODEL_DIR}")
        return LOCAL_MODEL_DIR
        
    except Exception as e:
        print(f"[MODEL] Error downloading model: {e}")
        print("[MODEL] Falling back to HuggingFace cache...")
        return MODEL_ID


def build_prompt(tokenizer, description: str, text: str) -> str:
    """Build formatted prompt for Maya1 TTS."""
    soh_token = tokenizer.decode([SOH_ID])
    eoh_token = tokenizer.decode([EOH_ID])
    soa_token = tokenizer.decode([SOA_ID])
    sos_token = tokenizer.decode([CODE_START_TOKEN_ID])
    eot_token = tokenizer.decode([TEXT_EOT_ID])
    bos_token = tokenizer.bos_token
    
    formatted_text = f'<description="{description}"> {text}'
    
    prompt = (
        soh_token + bos_token + formatted_text + eot_token +
        eoh_token + soa_token + sos_token
    )
    
    return prompt


def extract_snac_codes(token_ids: list) -> list:
    """Extract SNAC codes from generated tokens."""
    try:
        eos_idx = token_ids.index(CODE_END_TOKEN_ID)
    except ValueError:
        eos_idx = len(token_ids)
    
    snac_codes = [
        token_id for token_id in token_ids[:eos_idx]
        if SNAC_MIN_ID <= token_id <= SNAC_MAX_ID
    ]
    
    return snac_codes


def unpack_snac_from_7(snac_tokens: list) -> list:
    """Unpack 7-token SNAC frames to 3 hierarchical levels."""
    if snac_tokens and snac_tokens[-1] == CODE_END_TOKEN_ID:
        snac_tokens = snac_tokens[:-1]
    
    frames = len(snac_tokens) // SNAC_TOKENS_PER_FRAME
    snac_tokens = snac_tokens[:frames * SNAC_TOKENS_PER_FRAME]
    
    if frames == 0:
        return [[], [], []]
    
    l1, l2, l3 = [], [], []
    
    for i in range(frames):
        slots = snac_tokens[i*7:(i+1)*7]
        l1.append((slots[0] - CODE_TOKEN_OFFSET) % 4096)
        l2.extend([
            (slots[1] - CODE_TOKEN_OFFSET) % 4096,
            (slots[4] - CODE_TOKEN_OFFSET) % 4096,
        ])
        l3.extend([
            (slots[2] - CODE_TOKEN_OFFSET) % 4096,
            (slots[3] - CODE_TOKEN_OFFSET) % 4096,
            (slots[5] - CODE_TOKEN_OFFSET) % 4096,
            (slots[6] - CODE_TOKEN_OFFSET) % 4096,
        ])
    
    return [l1, l2, l3]


def decode_snac_to_audio(snac_tokens: list, snac_model, device: str) -> np.ndarray:
    """Decode SNAC tokens to audio waveform."""
    if len(snac_tokens) < 7:
        return None
    
    # Unpack SNAC tokens to 3 hierarchical levels
    levels = unpack_snac_from_7(snac_tokens)
    frames = len(levels[0])
    
    if frames == 0:
        return None
    
    # Convert to tensors
    codes_tensor = [
        torch.tensor(level, dtype=torch.long, device=device).unsqueeze(0)
        for level in levels
    ]
    
    # Decode to audio
    with torch.inference_mode():
        z_q = snac_model.quantizer.from_codes(codes_tensor)
        audio = snac_model.decoder(z_q)[0, 0].cpu().numpy()
    
    # Trim warmup samples (first 2048 samples as per README)
    if len(audio) > 2048:
        audio = audio[2048:]
    
    return audio


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
    """Estimate expected audio duration based on character count."""
    return len(text) / chars_per_second


def format_duration(seconds: float) -> str:
    """Format duration as MM:SS.ms"""
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:05.2f}"


def run_progressive_tests():
    """
    Run progressive text generation tests using NATIVE Maya1 TTS.
    """
    print("=" * 70)
    print("Maya1 Pipeline - Progressive Text Generation Test (NATIVE TTS)")
    print(f"Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\n[SETUP] Device: {device}")
    
    # Ensure model is downloaded locally
    model_path = ensure_model_downloaded()
    
    # Load Maya1 Model
    print("\n[SETUP] Loading Maya1 Model...")
    start_init = time.time()
    
    from transformers import AutoModelForCausalLM, AutoTokenizer
    
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True  # SECURITY: Only for trusted maya-research/maya1 model
    )
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=True  # SECURITY: Only for trusted maya-research/maya1 model
    )
    print(f"[SETUP] Maya1 Model loaded: {len(tokenizer)} tokens in vocabulary")
    
    # Load SNAC audio decoder
    print("[SETUP] Loading SNAC audio decoder (24kHz)...")
    from snac import SNAC
    snac_model = SNAC.from_pretrained(SNAC_MODEL_ID).eval()
    if device == "cuda":
        snac_model = snac_model.to(device)
    print("[SETUP] SNAC decoder loaded")
    
    init_time = time.time() - start_init
    print(f"[SETUP] Total initialization time: {init_time:.2f}s")
    
    # Create output directory
    output_dir = "generated_samples/maya1_native"
    os.makedirs(output_dir, exist_ok=True)
    print(f"[SETUP] Output directory: {output_dir}")
    
    # Voice description for consistent narrator voice
    voice_description = "Male narrator voice in his 40s with an American accent. Warm baritone, calm pacing, clear diction."
    print(f"[SETUP] Voice: {voice_description}")
    
    # Results tracking
    results = []
    all_passed = True
    
    print("\n" + "-" * 70)
    print("RUNNING PROGRESSIVE TESTS (NATIVE MAYA1 TTS)")
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
            # Build prompt
            prompt = build_prompt(tokenizer, voice_description, text)
            
            # Tokenize
            inputs = tokenizer(prompt, return_tensors="pt")
            input_len = inputs['input_ids'].shape[1]
            if device == "cuda":
                inputs = {k: v.to(device) for k, v in inputs.items()}
            
            print(f"  Input tokens: {input_len}")
            
            # Generate SNAC tokens
            start_gen = time.time()
            
            # Calculate max tokens based on expected duration
            # ~7 SNAC tokens per frame, ~47 frames per second
            expected_frames = int(expected_duration * 47)
            max_new_tokens = max(expected_frames * 7 * 2, 2048)  # 2x buffer + minimum
            
            with torch.inference_mode():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    min_new_tokens=28,  # At least 4 SNAC frames
                    temperature=0.4,
                    top_p=0.9,
                    repetition_penalty=1.1,
                    do_sample=True,
                    eos_token_id=CODE_END_TOKEN_ID,
                    pad_token_id=tokenizer.pad_token_id,
                )
            
            gen_time = time.time() - start_gen
            
            # Extract generated tokens
            generated_ids = outputs[0, input_len:].tolist()
            print(f"  Generated tokens: {len(generated_ids)}")
            
            # Extract SNAC codes
            snac_tokens = extract_snac_codes(generated_ids)
            print(f"  SNAC tokens: {len(snac_tokens)}")
            
            if len(snac_tokens) < 7:
                print(f"  Result: ✗ FAIL - Not enough SNAC tokens generated")
                all_passed = False
                results.append({
                    "level": level_name,
                    "chars": char_count,
                    "words": word_count,
                    "expected_sec": expected_duration,
                    "actual_sec": 0,
                    "deviation_pct": -100,
                    "file_size_kb": 0,
                    "gen_time_sec": gen_time,
                    "output_path": None,
                    "passed": False,
                    "error": "Not enough SNAC tokens",
                })
                continue
            
            # Decode to audio
            audio = decode_snac_to_audio(snac_tokens, snac_model, device)
            
            if audio is not None and len(audio) > 0:
                # Audio stats
                sample_rate = 24000
                actual_duration = len(audio) / sample_rate
                
                # Save file
                out_path = f"{output_dir}/test_{i}_{level_name.lower()}.wav"
                sf.write(out_path, audio, sample_rate)
                file_size = os.path.getsize(out_path)
                file_size_kb = file_size / 1024
                
                # Calculate deviation
                if expected_duration > 0:
                    deviation = ((actual_duration - expected_duration) / expected_duration) * 100
                else:
                    deviation = 0
                
                # Determine pass/fail (within 50% tolerance)
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
                print(f"  Result: ✗ FAIL - No audio decoded")
                all_passed = False
                results.append({
                    "level": level_name,
                    "chars": char_count,
                    "words": word_count,
                    "expected_sec": expected_duration,
                    "actual_sec": 0,
                    "deviation_pct": -100,
                    "file_size_kb": 0,
                    "gen_time_sec": gen_time,
                    "output_path": None,
                    "passed": False,
                    "error": "Audio decode failed",
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
    print("TEST SUMMARY (NATIVE MAYA1 TTS)")
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
        print("✓ ALL TESTS PASSED - Native Maya1 TTS is working correctly!")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("✗ SOME TESTS FAILED - Check results above for details")
        print("=" * 70)
    
    # Write log file
    log_path = f"{output_dir}/test_log.txt"
    with open(log_path, "w") as f:
        f.write(f"Maya1 Native TTS Progressive Test Log\n")
        f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Voice: {voice_description}\n")
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
            if 'error' in r:
                f.write(f"  Error: {r['error']}\n")
            f.write("\n")
        
        f.write(f"{'=' * 50}\n")
        f.write(f"Summary: {passed_count}/{total_count} tests passed\n")
    
    print(f"\nLog saved to: {log_path}")
    print(f"Audio files saved to: {output_dir}/")
    
    return all_passed


if __name__ == "__main__":
    success = run_progressive_tests()
    sys.exit(0 if success else 1)
