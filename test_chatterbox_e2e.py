#!/usr/bin/env python3
"""
End-to-end test for Chatterbox Turbo audiobook generation.
Tests: Text processing → Chunking → TTS → Stitching → M4B export
"""

import os
import sys
import time
from pathlib import Path

# Import existing pipeline components
from convert_epub_to_audiobook import clean_text, chunk_text_for_quality
from chatterbox_engine import ChatterboxTurboEngine, is_chatterbox_available
from assembler import stitch_audio_with_chapter_tracking, generate_chapter_metadata, export_m4b
import soundfile as sf
import numpy as np

# Test configuration
TEST_VOICE_SAMPLE = "voice_samples/SJ_FEMALE_22k.wav"  # Use SJ after conversion
OUTPUT_DIR = "output/e2e_test"
DEVICE = "cuda"  # or "cpu"

def test_chatterbox_e2e():
    """Run complete end-to-end test"""

    # 1. Setup
    print("=" * 60)
    print("Chatterbox E2E Test - Full Pipeline Validation")
    print("=" * 60)
    print()

    if not is_chatterbox_available():
        print("ERROR: chatterbox-tts not installed")
        print("Install with: pip install chatterbox-tts")
        return 1

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 2. Prepare test data
    chapters = prepare_test_chapters()
    print(f"Test configuration:")
    print(f"  Voice sample: {TEST_VOICE_SAMPLE}")
    print(f"  Chapters: {len(chapters)}")
    print(f"  Device: {DEVICE}")
    print(f"  Output: {OUTPUT_DIR}")
    print()

    # 3. Load Chatterbox engine
    print("Loading Chatterbox Turbo engine...")
    engine = ChatterboxTurboEngine(device=DEVICE)
    engine.load()
    print()

    # 4. Generate audio for each chapter
    chunk_files = []
    chunk_to_chapter = []  # Maps each chunk to chapter index
    chapter_titles = []
    total_gen_time = 0
    total_audio_duration = 0

    for i, chapter in enumerate(chapters):
        print(f"[Chapter {i+1}] {chapter['title']}")
        chapter_titles.append(chapter['title'])

        # Clean and chunk text
        cleaned = clean_text(chapter['content'])
        chunks = chunk_text_for_quality(cleaned, max_words=50)

        print(f"  Text chunks: {len(chunks)}")

        # Generate audio for each chunk
        for j, chunk in enumerate(chunks):
            word_count = len(chunk.split())
            print(f"    Chunk {j+1}/{len(chunks)}: {word_count} words")

            # Generate audio
            start_time = time.time()
            audio = engine.generate_audio(chunk, TEST_VOICE_SAMPLE)
            gen_time = time.time() - start_time
            total_gen_time += gen_time

            # Save chunk
            chunk_file = f"{OUTPUT_DIR}/ch{i+1}_chunk{j+1}.wav"
            sf.write(chunk_file, audio, engine.sr)
            chunk_files.append(chunk_file)
            chunk_to_chapter.append(i)  # Map this chunk to chapter i

            duration = len(audio) / engine.sr
            total_audio_duration += duration
            print(f"      ✓ {duration:.1f}s audio in {gen_time:.1f}s")

        print()

    # 5. Stitch audio files
    print("[Stitching] Combining audio chunks...")
    combined_wav = f"{OUTPUT_DIR}/combined.wav"
    _, chapter_markers = stitch_audio_with_chapter_tracking(
        chunk_files,
        chunk_to_chapter,
        chapter_titles,
        output_path=combined_wav
    )

    # Read combined file to get duration
    combined_audio, sr = sf.read(combined_wav)
    combined_duration = len(combined_audio) / sr
    print(f"  ✓ Combined: {combined_duration:.1f}s")
    print()

    # 6. Generate chapter metadata
    print("[Metadata] Creating chapter markers...")
    metadata_file = f"{OUTPUT_DIR}/chapters.txt"
    generate_chapter_metadata(chapter_markers, metadata_file)
    print(f"  ✓ Chapter metadata: {len(chapter_markers)} chapters")
    for marker in chapter_markers:
        print(f"    - {marker['title']}: {marker['start_ms']}ms - {marker['end_ms']}ms")
    print()

    # 7. Export to M4B
    print("[Export] Creating M4B file...")
    output_m4b = f"{OUTPUT_DIR}/test_audiobook.m4b"
    export_m4b(
        combined_wav,
        output_m4b,
        metadata={
            'title': 'Chatterbox E2E Test',
            'artist': 'Test Suite',
            'genre': 'Audiobook'
        },
        chapters_file=metadata_file,
        cover_art_path=None  # Optional: Add test cover
    )
    print()

    # 8. Validate output
    print("[Validation]")
    if os.path.exists(output_m4b):
        file_size = os.path.getsize(output_m4b) / 1024 / 1024
        print(f"  ✓ M4B created: {file_size:.2f} MB")
        print(f"  ✓ Output: {output_m4b}")
    else:
        print("  ✗ M4B creation failed!")
        return 1

    # 9. Performance metrics
    print()
    print("=" * 60)
    print("Performance Metrics")
    print("=" * 60)
    print(f"  Total chunks: {len(chunk_files)}")
    print(f"  Total generation time: {total_gen_time:.1f}s")
    print(f"  Total audio duration: {total_audio_duration:.1f}s")
    print(f"  Average gen time per chunk: {total_gen_time / len(chunk_files):.1f}s")
    print(f"  Real-time factor: {total_gen_time / total_audio_duration:.2f}x")
    print(f"  Combined file size: {os.path.getsize(combined_wav) / 1024 / 1024:.2f} MB")
    print(f"  M4B file size: {os.path.getsize(output_m4b) / 1024 / 1024:.2f} MB")
    print(f"  Compression ratio: {os.path.getsize(combined_wav) / os.path.getsize(output_m4b):.2f}x")
    print()

    # 10. Cleanup
    engine.cleanup()

    # Optional: Remove temp chunk files
    # for f in chunk_files:
    #     os.remove(f)

    print("=" * 60)
    print("Test Complete ✓")
    print("=" * 60)
    print()
    print("Next steps:")
    print(f"  1. Play M4B: vlc {output_m4b}")
    print(f"  2. Check chapters: ffmpeg -i {output_m4b}")
    print(f"  3. Listen to quality and voice cloning accuracy")
    print()

    return 0

def prepare_test_chapters():
    """Prepare test chapter data"""
    return [
        {
            "title": "Chapter 1: The Beginning",
            "content": """
            The morning sun broke through the clouds, casting golden
            rays across the valley. Sarah stood at the window, watching
            the world wake up. It was going to be a good day.

            She picked up her coffee mug and smiled. Today was the day
            everything would change. Little did she know how right she was.
            """
        },
        {
            "title": "Chapter 2: The Journey",
            "content": """
            The road stretched endlessly ahead, winding through forests
            and fields. Sarah's car hummed along steadily, mile after mile.

            She thought about her destination. What would she find there?
            Only time would tell. The radio crackled with static, playing
            old songs that reminded her of home.
            """
        },
        {
            "title": "Chapter 3: Arrival",
            "content": """
            The town appeared on the horizon just as the sun began to set.
            Victorian houses lined the streets, their windows glowing warmly
            in the fading light.

            Sarah parked her car and stepped out, breathing in the cool
            evening air. This was it. Her new beginning. Whatever came next,
            she was ready for it.
            """
        }
    ]

if __name__ == "__main__":
    sys.exit(test_chatterbox_e2e())
