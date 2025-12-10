import os
from pydub import AudioSegment
import subprocess

def stitch_audio(audio_chunks, output_path="temp_book.wav"):
    """
    Stitches audio chunks with exactly 400ms of silence between them.
    audio_chunks: List of paths to audio files or AudioSegment objects.
    """
    combined = AudioSegment.empty()
    silence_400ms = AudioSegment.silent(duration=400)

    for i, chunk in enumerate(audio_chunks):
        if isinstance(chunk, str):
            segment = AudioSegment.from_file(chunk)
        else:
            segment = chunk
        
        combined += segment
        
        # Add silence between chunks, but maybe not after the very last one?
        # Prompt says "Insert exactly 400ms of silence between sentences to create natural pacing."
        # Assuming chunks represent grouped sentences.
        if i < len(audio_chunks) - 1:
            combined += silence_400ms

    combined.export(output_path, format="wav")
    return output_path

def export_m4b(wav_path, output_m4b_path, metadata=None, cover_art_path=None):
    """
    Converts WAV to M4B with metadata using ffmpeg.
    metadata: dict with 'title', 'author'.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", wav_path,
    ]

    if cover_art_path:
        cmd.extend(["-i", cover_art_path, "-map", "0:a", "-map", "1", "-c:v", "copy", "-disposition:v:0", "attached_pic"])
    
    cmd.extend(["-c:a", "aac", "-b:a", "64k"]) # Standard audiobook settings

    if metadata:
        if "title" in metadata:
            cmd.extend(["-metadata", f"title={metadata['title']}"])
        if "author" in metadata:
            cmd.extend(["-metadata", f"artist={metadata['author']}"]) 

    cmd.append(output_m4b_path)
    
    print(f"Running command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

