"""
Conversion Worker for WebUI

Extracted conversion logic from main.py adapted for state-based updates.
Runs in a background thread and updates the global ConversionState.
"""

import os
import sys
import time

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversion_state import ConversionState
from epub_parser import parse_epub_with_chapters
from progress_manager import ConversionProgress, save_progress, load_progress, cleanup_progress


def run_conversion_job(
    epub_path: str,
    output_dir: str,
    selected_chapters: list,
    voice_preset_id: str,
    state: ConversionState
):
    """
    Main conversion orchestration (adapted from main.py:608-886).
    Updates ConversionState instead of GUI.

    Supports both Maya1 and Chatterbox Turbo engines via voice preset selection.

    Args:
        epub_path: Path to the EPUB file
        output_dir: Directory for output files
        selected_chapters: List of chapter indices to convert
        voice_preset_id: Voice preset ID (determines engine and voice settings)
        state: ConversionState object for progress tracking
    """
    try:
        state.add_log("Importing modules...")

        # Import heavy modules here to not slow down startup
        from convert_epub_to_audiobook import Maya1TTSEngine, clean_text, chunk_text_for_quality, LOCAL_MODEL_DIR
        from assembler import stitch_audio_with_chapter_tracking, generate_chapter_metadata, export_m4b, create_audiobookshelf_folder
        from epub_parser import get_cover_extension
        import soundfile as sf
        import torch

        # Import validate_voice_preset from server module
        from webview_server import validate_voice_preset

        # Validate and get voice preset configuration
        state.add_log(f"Loading voice preset: {voice_preset_id}")
        preset = validate_voice_preset(voice_preset_id)
        engine_type = preset.get("engine", "maya1")  # Default to Maya1

        state.add_log(f"Selected engine: {engine_type}")

        os.makedirs(output_dir, exist_ok=True)

        temp_dir = os.path.join(output_dir, "temp_chunks")
        os.makedirs(temp_dir, exist_ok=True)

        # Parse EPUB
        state.add_log("Processing chapters...")
        state.update_progress(2, "Parsing EPUB...")

        parsed_epub = parse_epub_with_chapters(epub_path)

        # Prepare chunks from selected chapters
        all_chunks = []
        chunk_to_chapter = []
        chapter_titles = []

        for chapter in parsed_epub.chapters:
            if chapter.order not in selected_chapters:
                continue

            chapter_titles.append(chapter.title)
            chapter_idx = len(chapter_titles) - 1

            cleaned = clean_text(chapter.content)
            # Keep Chatterbox-friendly chunk sizes (~40 words) for better quality
            chunks = chunk_text_for_quality(cleaned, max_words=40, min_words=15)

            for chunk in chunks:
                all_chunks.append(chunk)
                chunk_to_chapter.append(chapter_idx)

        total_chunks = len(all_chunks)
        state.add_log(f"Total chunks: {total_chunks}")

        # Update total chunks in state
        with state.lock:
            state.total_chunks = total_chunks

        # Check for resume
        start_idx = 0
        chunk_files = {}

        resumable = load_progress(output_dir)
        if resumable and os.path.normpath(resumable.epub_path) == os.path.normpath(epub_path):
            for idx, path in resumable.chunk_files.items():
                if os.path.exists(path):
                    chunk_files[idx] = path
                    start_idx = max(start_idx, idx + 1)

            if start_idx > 0:
                state.add_log(f"Resuming from chunk {start_idx}")

        # Initialize progress
        progress = ConversionProgress(
            epub_path=epub_path,
            output_dir=output_dir,
            selected_chapters=selected_chapters,
            voice_prompt=preset.get("prompt", "") or preset.get("reference_audio", ""),  # Store voice config
            total_chunks=total_chunks,
            completed_chunks=list(chunk_files.keys()),
            chunk_files=chunk_files,
            chunk_to_chapter=chunk_to_chapter,
            chapter_titles=chapter_titles
        )

        # Load TTS engine based on preset
        state.add_log("Loading model...")
        state.update_progress(5, "Loading TTS model...")

        device = "cuda" if torch.cuda.is_available() else "cpu"

        if engine_type == "chatterbox":
            # Load Chatterbox Turbo engine
            from chatterbox_engine import ChatterboxTurboEngine

            state.add_log("Loading Chatterbox Turbo...")
            engine = ChatterboxTurboEngine(device=device)
            engine.load()
            sample_rate = 22050  # Chatterbox outputs 22.05kHz
            reference_audio = preset["reference_audio"]

            state.add_log(f"Chatterbox Turbo loaded (reference: {os.path.basename(reference_audio)})")

        else:  # maya1 (default)
            # Load Maya1 engine
            state.add_log("Loading Maya1...")
            engine = Maya1TTSEngine(LOCAL_MODEL_DIR, device)
            engine.load()
            sample_rate = 24000  # Maya1 outputs 24kHz
            voice_prompt = preset["prompt"]

            state.add_log("Maya1 loaded")

        state.update_progress(10, "Generating audio...")

        # Generate chunks sequentially
        for i in range(start_idx, total_chunks):
            # Check cancel
            if state.cancel_event.is_set():
                save_progress(output_dir, progress)
                state.add_log("Cancelled - progress saved", "warning")
                state.set_status("cancelled")
                return

            # Wait if paused
            while state.pause_event.is_set() and not state.cancel_event.is_set():
                time.sleep(0.5)

            # Check cancel again after pause
            if state.cancel_event.is_set():
                save_progress(output_dir, progress)
                state.add_log("Cancelled - progress saved", "warning")
                state.set_status("cancelled")
                return

            chunk = all_chunks[i]
            chapter_title = chapter_titles[chunk_to_chapter[i]]

            status_text = f"Chunk {i+1}/{total_chunks} | {chapter_title}"
            state.update_progress(10 + (i / total_chunks) * 75, status_text)

            try:
                # Generate audio with engine-specific parameters
                if engine_type == "chatterbox":
                    # Debug: Log chunk text and length
                    state.add_log(f"[DEBUG] Chunk {i+1} length: {len(chunk)} chars, words: {len(chunk.split())}")
                    state.add_log(f"[DEBUG] Chunk text preview: {chunk[:100]}...")
                    # Persist full chunk text for postmortem analysis
                    try:
                        debug_text_path = os.path.join(temp_dir, f"chunk_{i:04d}.txt")
                        with open(debug_text_path, "w", encoding="utf-8") as f:
                            f.write(chunk)
                        print(f"[DEBUG] Saved chunk text to {debug_text_path}", flush=True)
                    except Exception as e:
                        state.add_log(f"[DEBUG] Failed to write chunk text: {e}")

                    audio = engine.generate_audio(
                        text=chunk,
                        reference_audio_path=reference_audio,
                        max_duration_sec=60
                    )

                    # Debug: Log audio stats
                    if audio is not None:
                        state.add_log(f"[DEBUG] Audio shape: {audio.shape}, dtype: {audio.dtype}, range: [{audio.min():.3f}, {audio.max():.3f}]")
                else:  # maya1
                    audio = engine.generate_audio(
                        text=chunk,
                        voice_description=voice_prompt,
                        max_duration_sec=60
                    )

                if audio is not None and len(audio) > 0:
                    chunk_path = os.path.join(temp_dir, f"chunk_{i:04d}.wav")
                    sf.write(chunk_path, audio, sample_rate)

                    progress.completed_chunks.append(i)
                    progress.chunk_files[i] = chunk_path

                    # Save progress after each chunk
                    save_progress(output_dir, progress)

                    # Update state
                    with state.lock:
                        state.current_chunk = i + 1
                else:
                    state.add_log(f"Warning: Empty audio for chunk {i}", "warning")

            except Exception as e:
                state.add_log(f"Error on chunk {i}: {e}", "error")
                import traceback
                traceback.print_exc()

        # Check if cancelled before stitching
        if state.cancel_event.is_set():
            save_progress(output_dir, progress)
            state.add_log("Cancelled - progress saved", "warning")
            state.set_status("cancelled")
            return

        # Stitch audio
        state.add_log("Stitching audio...")
        state.update_progress(86, "Stitching audio...")

        audio_files = [progress.chunk_files[i] for i in sorted(progress.chunk_files.keys())]
        chunk_mapping = [progress.chunk_to_chapter[i] for i in sorted(progress.chunk_files.keys())]

        output_wav, chapters_info = stitch_audio_with_chapter_tracking(
            audio_files,
            chunk_mapping,
            chapter_titles,
            output_path=os.path.join(output_dir, "temp_combined.wav")
        )

        # Generate chapters
        state.add_log("Adding chapters...")
        state.update_progress(90, "Adding chapter markers...")

        chapters_file = generate_chapter_metadata(
            chapters_info,
            os.path.join(output_dir, "chapters.txt")
        )

        # Save cover
        cover_path = None
        if parsed_epub.cover_image:
            ext = get_cover_extension(parsed_epub.cover_media_type or "image/jpeg")
            cover_path = os.path.join(output_dir, f"temp_cover{ext}")
            with open(cover_path, 'wb') as f:
                f.write(parsed_epub.cover_image)

        # Export M4B
        state.add_log("Exporting M4B...")
        state.update_progress(92, "Exporting M4B...")

        temp_m4b = os.path.join(output_dir, "temp_output.m4b")
        meta = {'title': parsed_epub.title, 'author': parsed_epub.author}

        export_m4b(output_wav, temp_m4b, metadata=meta, cover_art_path=cover_path, chapters_file=chapters_file)

        # Create Audiobookshelf folder
        state.add_log("Organizing files...")
        state.update_progress(95, "Organizing files...")

        final_path = create_audiobookshelf_folder(
            output_dir=output_dir,
            author=parsed_epub.author,
            title=parsed_epub.title,
            m4b_path=temp_m4b,
            cover_image_bytes=parsed_epub.cover_image,
            cover_extension=get_cover_extension(parsed_epub.cover_media_type or "image/jpeg")
        )

        # Cleanup
        state.add_log("Cleaning up...")
        state.update_progress(98, "Cleaning up...")

        for path in audio_files:
            try:
                os.remove(path)
            except OSError as e:
                state.add_log(f"Warning: Failed to remove {path}: {e}", "warning")

        for temp in [output_wav, chapters_file, cover_path, temp_m4b]:
            if temp and os.path.exists(temp):
                try:
                    os.remove(temp)
                except OSError as e:
                    state.add_log(f"Warning: Failed to remove {temp}: {e}", "warning")

        try:
            os.rmdir(temp_dir)
        except OSError as e:
            state.add_log(f"Warning: Failed to remove temp directory: {e}", "warning")

        cleanup_progress(output_dir)

        # Mark complete
        state.add_log(f"Conversion complete! Saved to: {final_path}", "success")
        state.set_completed(final_path)

    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        state.set_error(error_msg)
