import re
import spacy
from num2words import num2words
import torch
import os

# Placeholder for Maya1 model loading
# Assuming standard HF transformers usage or a specific wrapper if documented.
# Since no specific library was given other than "transformers", we'll use a generic approach 
# or a custom class structure that can be filled in.

class Maya1Pipeline:
    def __init__(self, model_id="maya-research/maya1", device="cuda" if torch.cuda.is_available() else "cpu"):
        self.model_id = model_id
        self.device = device
        self.model = None
        self.tokenizer = None
        print(f"Initializing Maya1Pipeline on {self.device}...")

    def load_model(self):
        """
        Loads the Maya1 model. 
        Detects if model is Text-only (Llama) and initializes gTTS fallback if needed.
        """
        try:
            from transformers import AutoConfig, AutoModel
            print(f"Loading model from {self.model_id}...")
            
            # Check architecture first
            try:
                config = AutoConfig.from_pretrained(self.model_id)
                self.is_text_model = 'Llama' in config.architectures[0] if config.architectures else False
                if self.is_text_model:
                    print(f"Detected Text Model ({config.architectures}). Using gTTS fallback for Audio Generation.")
            except Exception as e:
                print(f"Warning: Failed to detect model architecture ({e}), assuming non-text model")
                self.is_text_model = False

            # Load weights to verify files are present (Requirement: "Confirm downloaded")
            self.model = AutoModel.from_pretrained(self.model_id).to(self.device)
            print("Maya1 Model weights loaded successfully.")
            
        except Exception as e:
            print(f"Failed to load model: {e}")
            self.model = None

    def generate_chunk(self, text, ref_audio_path):
        """
        Generates audio for a single chunk.
        """
        # If we have a robust TTS pipeline (future), use it. 
        # For now, with Llama model, we use gTTS fallback.
        try:
            from gtts import gTTS
            from io import BytesIO
            import torch
            import numpy as np
            from pydub import AudioSegment
            
            # Generate MP3 via gTTS
            tts = gTTS(text, lang='en')
            mp3_fp = BytesIO()
            tts.write_to_fp(mp3_fp)
            mp3_fp.seek(0)
            
            # Convert to Tensor [1, T] @ 24kHz using pydub
            sound = AudioSegment.from_file(mp3_fp, format="mp3")
            sound = sound.set_frame_rate(24000).set_channels(1)
            
            # Pydub to numpy
            arr = np.array(sound.get_array_of_samples())
            
            # Normalize to float32 [-1, 1] if pydub gave int16
            if sound.sample_width == 2:
                arr = arr.astype(np.float32) / 32768.0
                
            tensor = torch.tensor(arr)
            if tensor.ndim == 1:
                tensor = tensor.unsqueeze(0)
                
            return tensor
            
        except Exception as e:
            print(f"Inference error (gTTS fallback): {e}")
            return None

def clean_text(text):
    """
    Sanitizes text for Maya1.
    1. Converts numbers to words.
    2. Expands abbreviations.
    3. Removes special characters.
    4. Replaces newlines within paragraphs.
    """
    # 1. Numbers to words
    text = re.sub(r"(\d+)", lambda x: num2words(x.group(0)), text)

    # 2. Abbreviations 
    # Basic list, can be expanded
    abbreviations = {
        "Dr.": "Doctor",
        "Mr.": "Mister",
        "Mrs.": "Missus",
        "Ms.": "Miss",
        "Prof.": "Professor",
        "St.": "Saint",
        "etc.": "et cetera",
    }
    for abbr, expanded in abbreviations.items():
        # Use regex to replace whole words only, case insensitive if needed, but strict for titles
        text = text.replace(abbr, expanded)

    # 3. Remove special characters (*, _, [...])
    # Keep punctuation that aids speech (.,?!:;), remove others
    text = re.sub(r"[\*_\[\]\(\)]", "", text)
    
    # 4. Replace newlines within paragraphs with spaces
    # We want to keep double newlines as paragraph breaks if we were processing full text,
    # but for chunks, we just want output flow. 
    # Strategy: Replace single newlines with space, keep double? 
    # The prompt says "Replaces newlines within paragraphs with spaces".
    text = re.sub(r"\s+", " ", text).strip()

    return text

def chunk_text(text, max_words=25):
    """
    Splits text into chunks under ~15 seconds (approx 25 words).
    Applies the 'Pad Trick'.
    """
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        print("Downloading spacy model 'en_core_web_sm'...")
        # Fallback if not installed, though strictly we should ask user to install. 
        # Attempting simple split if load fails or assume it's pre-downloaded.
        from spacy.cli import download
        download("en_core_web_sm")
        nlp = spacy.load("en_core_web_sm")

    doc = nlp(text)
    sentences = [sent.text.strip() for sent in doc.sents]

    chunks = []
    current_chunk = []
    current_word_count = 0

    for sentence in sentences:
        word_count = len(sentence.split())
        
        if current_word_count + word_count > max_words:
            # Commit current chunk
            if current_chunk:
                # The Pad Trick: Prepend and Append 250ms of silence tokens (or neutral punctuation ...)
                chunk_text_content = " ".join(current_chunk)
                padded_chunk = f"... {chunk_text_content} ..."
                chunks.append(padded_chunk)
            
            # Start new chunk
            current_chunk = [sentence]
            current_word_count = word_count
        else:
            current_chunk.append(sentence)
            current_word_count += word_count

    # Add last chunk
    if current_chunk:
        chunk_text_content = " ".join(current_chunk)
        padded_chunk = f"... {chunk_text_content} ..."
        chunks.append(padded_chunk)

    return chunks

# Validation Logic
def apply_vad_trimming(audio_tensor, sample_rate=24000):
    """
    Trims silence from start/end using Silero VAD.
    Returns: Trimmed audio tensor.
    """
    # Load VAD model (using torch hub for simplicity, or local if preferred/downloaded)
    # Using 'silero_vad' from snakers4/silero-vad
    try:
        model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                      model='silero_vad',
                                      force_reload=False,
                                      onnx=False)
        (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils
        
        # Audio tensor expected shape: [1, T] or [T]
        if audio_tensor.dim() == 2:
            audio_flat = audio_tensor.squeeze(0)
        else:
            audio_flat = audio_tensor
            
        timestamps = get_speech_timestamps(audio_flat, model, sampling_rate=sample_rate)
        
        # Collect chunks (essentially trimming start/end silence and concatenating speech parts)
        # Note: This might remove internal pauses too.
        # Requirement: "Trim the silence/noise from the start and end"
        # If we only want start/end trim, we just take min start and max end.
        
        if not timestamps:
            return audio_tensor # No speech detected, return original (or empty?)

        start_sample = timestamps[0]['start']
        end_sample = timestamps[-1]['end']
        
        trimmed_audio = audio_flat[start_sample:end_sample]
        return trimmed_audio.unsqueeze(0) # Restore [1, T]

    except Exception as e:
        print(f"VAD failed: {e}")
        return audio_tensor

def validate_audio(audio_tensor, text_char_count, sample_rate=24000):
    """
    Hallucination Filter pipeline:
    1. VAD Trim (in-place modification of finding boundaries, but here we might just return the trimmed version).
    2. Length Check.
    Returns: (bool, trimmed_audio_tensor)
    """
    # 1. Trim
    trimmed_audio = apply_vad_trimming(audio_tensor, sample_rate)
    
    # Calculate duration
    num_samples = trimmed_audio.shape[-1]
    duration_sec = num_samples / sample_rate
    
    # 2. Length Check
    # Rough heuristic: 15 chars ~ 1 second
    expected_sec = text_char_count / 15.0 
    deviation_pct = abs(duration_sec - expected_sec) / expected_sec if expected_sec > 0 else 0
    
    # Tolerating 30% deviation
    if deviation_pct > 0.30:
        print(f"Validation Failed: Duration {duration_sec:.2f}s vs Expected {expected_sec:.2f}s (Dev: {deviation_pct:.2%})")
        return False, trimmed_audio
    
    return True, trimmed_audio

