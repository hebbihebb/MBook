#!/usr/bin/env python3
"""
EPUB to M4B Audiobook Converter using Native Maya1 TTS

This script converts an EPUB file to an M4B audiobook using the
Maya1 3B-parameter TTS model with SNAC neural codec.

Quality target: Similar to test_3_medium.wav (~0.3% deviation)
"""

import os
import sys
import time
import datetime
import re
import subprocess
import logging
import traceback
import atexit
import signal

# Ensure imports work
sys.path.append(os.getcwd())

import torch
import numpy as np
import soundfile as sf
from scipy.io import wavfile

# Load spacy model once at module level for performance
_SPACY_NLP = None

def get_spacy_model():
    """Get or load spacy model (singleton pattern)."""
    global _SPACY_NLP
    if _SPACY_NLP is None:
        try:
            import spacy
            _SPACY_NLP = spacy.load("en_core_web_sm")
        except Exception as e:
            print(f"[CHUNK] Warning: Failed to load spacy model ({e}), will fall back to simple splitting")
            _SPACY_NLP = False  # Mark as failed to avoid retrying
    return _SPACY_NLP if _SPACY_NLP is not False else None

# Maya1 Token Constants
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

# Paths
LOCAL_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "maya1")
SNAC_MODEL_ID = "hubertsiuzdak/snac_24khz"

# Global logger
logger = None

def setup_logging(output_dir: str, epub_name: str) -> logging.Logger:
    """
    Setup logging to both console and file.
    Log file is saved to output_dir with timestamp.
    """
    global logger
    
    # Create logger
    logger = logging.getLogger('audiobook_converter')
    logger.setLevel(logging.DEBUG)
    
    # Clear any existing handlers
    logger.handlers = []
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter('%(message)s')
    
    # File handler - persistent log
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f"conversion_{epub_name}_{timestamp}.log"
    log_path = os.path.join(output_dir, log_filename)
    
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"Log file: {log_path}")
    
    return logger


class Maya1TTSEngine:
    """Native Maya1 TTS engine using SNAC codec."""
    
    def __init__(self, model_path: str, device: str = "cuda"):
        self.model_path = model_path
        self.device = device
        self.model = None
        self.tokenizer = None
        self.snac_model = None
    
    def load(self):
        """Load all models."""
        import warnings

        print("[ENGINE] Loading Maya1 model...")

        from transformers import AutoModelForCausalLM, AutoTokenizer
        from snac import SNAC

        try:
            # SECURITY WARNING: trust_remote_code=True allows arbitrary code execution
            # from HuggingFace Hub. Only use with trusted models like maya-research/maya1.
            # If the model repository is compromised, malicious code could execute.
            # For production use, consider downloading models locally and auditing code.
            warnings.warn(
                "Loading model with trust_remote_code=True. This allows arbitrary code "
                "execution from the model repository. Only use with trusted sources like "
                "maya-research/maya1.",
                RuntimeWarning,
                stacklevel=2
            )
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True  # Required for Maya1 custom architecture
            )
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                trust_remote_code=True  # Required for Maya1 custom tokenizer
            )
            print(f"[ENGINE] Maya1 loaded: {len(self.tokenizer)} tokens")

            print("[ENGINE] Loading SNAC decoder...")
            self.snac_model = SNAC.from_pretrained(SNAC_MODEL_ID).eval()
            if self.device == "cuda":
                self.snac_model = self.snac_model.to(self.device)
            print("[ENGINE] SNAC decoder loaded")
        except Exception as e:
            # Clean up any partially loaded models
            self.cleanup()
            raise RuntimeError(f"Failed to load models: {e}") from e

    def cleanup(self):
        """Clean up GPU/CPU resources."""
        # Clean each resource independently to prevent one failure from blocking others
        if hasattr(self, 'model') and self.model is not None:
            try:
                del self.model
                self.model = None
                print("[ENGINE] Maya1 model released")
            except Exception as e:
                print(f"[ENGINE] Warning: Failed to release model: {e}")

        if hasattr(self, 'snac_model') and self.snac_model is not None:
            try:
                del self.snac_model
                self.snac_model = None
                print("[ENGINE] SNAC model released")
            except Exception as e:
                print(f"[ENGINE] Warning: Failed to release SNAC model: {e}")

        if hasattr(self, 'tokenizer') and self.tokenizer is not None:
            try:
                del self.tokenizer
                self.tokenizer = None
            except Exception as e:
                print(f"[ENGINE] Warning: Failed to release tokenizer: {e}")

        # Always attempt cleanup, regardless of failures above
        try:
            import gc
            gc.collect()
            if self.device == "cuda":
                torch.cuda.empty_cache()
                print("[ENGINE] CUDA cache cleared")
        except Exception as e:
            print(f"[ENGINE] Warning: Failed to clear CUDA cache: {e}")
    
    def build_prompt(self, description: str, text: str) -> str:
        """Build formatted prompt for Maya1 TTS."""
        soh_token = self.tokenizer.decode([SOH_ID])
        eoh_token = self.tokenizer.decode([EOH_ID])
        soa_token = self.tokenizer.decode([SOA_ID])
        sos_token = self.tokenizer.decode([CODE_START_TOKEN_ID])
        eot_token = self.tokenizer.decode([TEXT_EOT_ID])
        bos_token = self.tokenizer.bos_token
        
        formatted_text = f'<description="{description}"> {text}'
        
        prompt = (
            soh_token + bos_token + formatted_text + eot_token +
            eoh_token + soa_token + sos_token
        )
        
        return prompt
    
    def generate_audio(self, text: str, voice_description: str, max_duration_sec: float = 30.0) -> np.ndarray:
        """Generate audio for a text chunk."""
        # Validate voice_description
        if not voice_description or not voice_description.strip():
            raise ValueError("voice_description cannot be empty")
        if len(voice_description) > 1000:
            raise ValueError(f"voice_description too long ({len(voice_description)} chars, max 1000)")

        prompt = self.build_prompt(voice_description, text)
        
        inputs = self.tokenizer(prompt, return_tensors="pt")
        input_len = inputs['input_ids'].shape[1]
        
        if self.device == "cuda":
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Calculate max tokens based on expected duration
        # ~7 SNAC tokens per frame, ~47 frames per second
        expected_frames = int(max_duration_sec * 47)
        max_new_tokens = max(expected_frames * 7, 2048)
        
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                min_new_tokens=28,
                temperature=0.4,
                top_p=0.9,
                repetition_penalty=1.1,
                do_sample=True,
                eos_token_id=CODE_END_TOKEN_ID,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        
        # Extract generated tokens
        generated_ids = outputs[0, input_len:].tolist()
        
        # Extract SNAC codes
        snac_tokens = self._extract_snac_codes(generated_ids)
        
        if len(snac_tokens) < 7:
            return None
        
        # Decode to audio
        audio = self._decode_snac(snac_tokens)
        return audio
    
    def _extract_snac_codes(self, token_ids: list) -> list:
        """Extract SNAC codes from generated tokens."""
        try:
            eos_idx = token_ids.index(CODE_END_TOKEN_ID)
        except ValueError:
            eos_idx = len(token_ids)
        
        return [
            token_id for token_id in token_ids[:eos_idx]
            if SNAC_MIN_ID <= token_id <= SNAC_MAX_ID
        ]
    
    def _unpack_snac(self, snac_tokens: list) -> list:
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
    
    def _decode_snac(self, snac_tokens: list) -> np.ndarray:
        """Decode SNAC tokens to audio waveform."""
        levels = self._unpack_snac(snac_tokens)
        
        if len(levels[0]) == 0:
            return None
        
        codes_tensor = [
            torch.tensor(level, dtype=torch.long, device=self.device).unsqueeze(0)
            for level in levels
        ]
        
        with torch.inference_mode():
            z_q = self.snac_model.quantizer.from_codes(codes_tensor)
            audio = self.snac_model.decoder(z_q)[0, 0].cpu().numpy()
        
        # Trim warmup samples
        if len(audio) > 2048:
            audio = audio[2048:]
        
        return audio


def clean_text(text: str) -> str:
    """Clean text for TTS."""
    from num2words import num2words
    
    # Smart quotes to regular quotes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    text = text.replace('—', ' - ').replace('–', ' - ')
    text = text.replace('…', '...')
    
    # Numbers to words (for better pronunciation)
    text = re.sub(r"(\d+)", lambda x: num2words(int(x.group(0))), text)
    
    # Abbreviations
    abbreviations = {
        "Dr.": "Doctor",
        "Mr.": "Mister",
        "Mrs.": "Missus",
        "Ms.": "Miss",
        "Prof.": "Professor",
        "St.": "Saint",
        "etc.": "et cetera",
        "vs.": "versus",
        "i.e.": "that is",
        "e.g.": "for example",
    }
    for abbr, expanded in abbreviations.items():
        text = text.replace(abbr, expanded)
    
    # Remove special characters but keep punctuation for speech
    text = re.sub(r"[\*_\[\]\(\)~`#]", "", text)
    
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    
    return text


def chunk_text_for_quality(text: str, max_words: int = 40, min_words: int = 10) -> list:
    """
    Chunk text into optimal sizes for high-quality TTS.

    For best quality (similar to medium test), we want chunks around 40-60 words.
    This produces ~20-30 second audio segments which Maya1 handles well.

    Handles very large texts by processing in batches.
    """

    # Load spacy model (using singleton to avoid reloading)
    nlp = get_spacy_model()

    if nlp is None:
        # Fallback to simple sentence splitting if spacy is not available
        print("[CHUNK] Using simple sentence splitting (spacy not available)")
        sentences = []
        for sent in text.split('. '):
            if sent.strip():
                sentences.append(sent.strip() + ".")

        # Chunk sentences by word count
        chunks = []
        current_chunk = []
        current_words = 0

        for sent in sentences:
            word_count = len(sent.split())
            if current_words + word_count > max_words and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sent]
                current_words = word_count
            else:
                current_chunk.append(sent)
                current_words += word_count

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    # Increase max length for large texts
    nlp.max_length = 2000000
    
    # For very large texts, process in chunks to avoid memory issues
    # Split by paragraphs first
    paragraphs = text.split('\n\n')
    
    all_sentences = []
    batch_text = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # If adding this paragraph keeps us under 500k chars, add it
        if len(batch_text) + len(para) < 500000:
            batch_text += para + " "
        else:
            # Process current batch
            if batch_text:
                try:
                    doc = nlp(batch_text)
                    all_sentences.extend([sent.text.strip() for sent in doc.sents if sent.text.strip()])
                except Exception as e:
                    # Fallback: simple sentence splitting
                    all_sentences.extend([s.strip() + "." for s in batch_text.split('. ') if s.strip()])
            batch_text = para + " "
    
    # Process remaining batch
    if batch_text:
        try:
            doc = nlp(batch_text)
            all_sentences.extend([sent.text.strip() for sent in doc.sents if sent.text.strip()])
        except Exception as e:
            print(f"[CHUNK] Warning: spaCy sentence parsing failed ({e}), falling back to simple split")
            all_sentences.extend([s.strip() + "." for s in batch_text.split('. ') if s.strip()])
    
    print(f"[CHUNK] Extracted {len(all_sentences)} sentences")
    
    # Now chunk sentences into groups
    chunks = []
    current_chunk = []
    current_word_count = 0
    
    for sentence in all_sentences:
        word_count = len(sentence.split())
        
        # If adding this sentence exceeds max, commit current chunk
        if current_word_count + word_count > max_words and current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(chunk_text)
            current_chunk = []
            current_word_count = 0
        
        current_chunk.append(sentence)
        current_word_count += word_count
        
        # If single sentence exceeds max, commit it alone
        if current_word_count >= max_words:
            chunk_text = " ".join(current_chunk)
            chunks.append(chunk_text)
            current_chunk = []
            current_word_count = 0
    
    # Add remaining chunk
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        # If too small, merge with previous
        if len(chunks) > 0 and current_word_count < min_words:
            chunks[-1] = chunks[-1] + " " + chunk_text
        else:
            chunks.append(chunk_text)
    
    return chunks


def parse_epub(epub_path: str) -> tuple:
    """Parse EPUB and extract text and metadata."""
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
    
    print(f"[EPUB] Reading: {epub_path}")
    book = epub.read_epub(epub_path)
    
    # Extract metadata
    title = book.title or "Unknown Title"
    author = "Unknown Author"
    try:
        creators = book.get_metadata('DC', 'creator')
        if creators:
            author = creators[0][0]
    except Exception as e:
        print(f"[EPUB] Warning: Failed to extract metadata: {e}")
    
    print(f"[EPUB] Title: {title}")
    print(f"[EPUB] Author: {author}")
    
    # Extract text from all document items
    full_text = ""
    chapter_count = 0
    
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            text = soup.get_text(separator=" ")
            text = text.strip()
            
            if text and len(text) > 50:  # Skip very short items
                full_text += text + "\n\n"
                chapter_count += 1
    
    print(f"[EPUB] Extracted text from {chapter_count} chapters")
    print(f"[EPUB] Total characters: {len(full_text)}")
    
    return full_text, {"title": title, "author": author}


def stitch_audio_files(audio_files: list, output_path: str, silence_ms: int = 400) -> str:
    """Stitch audio files together with silence between them."""
    from pydub import AudioSegment
    
    combined = AudioSegment.empty()
    silence = AudioSegment.silent(duration=silence_ms)
    
    for i, audio_file in enumerate(audio_files):
        segment = AudioSegment.from_file(audio_file)
        combined += segment
        
        if i < len(audio_files) - 1:
            combined += silence
    
    combined.export(output_path, format="wav")
    return output_path


def export_m4b(wav_path: str, output_path: str, metadata: dict):
    """Convert WAV to M4B using ffmpeg."""
    # Import from assembler
    from assembler import sanitize_metadata, check_ffmpeg_available

    # Check ffmpeg availability before proceeding
    check_ffmpeg_available()

    cmd = [
        "ffmpeg", "-y",
        "-i", wav_path,
        "-c:a", "aac",
        "-b:a", "128k",  # Higher bitrate for better quality
        "-ar", "24000",
    ]

    # Apply metadata (sanitized to prevent command injection)
    if metadata:
        if "title" in metadata:
            safe_title = sanitize_metadata(metadata['title'])
            cmd.extend(["-metadata", f"title={safe_title}"])
        if "author" in metadata:
            safe_author = sanitize_metadata(metadata['author'])
            cmd.extend(["-metadata", f"artist={safe_author}"])
    
    cmd.append(output_path)
    
    print(f"[M4B] Running ffmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[M4B] Error: {result.stderr}")
        raise RuntimeError("ffmpeg failed")
    
    return output_path


def convert_epub_to_audiobook(epub_path: str, output_dir: str = None, voice: str = None, max_chunks: int = None):
    """
    Main conversion function.
    
    Args:
        epub_path: Path to EPUB file
        output_dir: Output directory (default: audiobook_output next to EPUB)
        voice: Voice description for TTS
        max_chunks: Maximum number of chunks to process (for testing). None = all chunks.
    """
    global logger
    
    # Setup paths first (needed for logging)
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(epub_path) or ".", "audiobook_output")
    os.makedirs(output_dir, exist_ok=True)
    
    temp_dir = os.path.join(output_dir, "temp_chunks")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Setup logging
    epub_basename = os.path.splitext(os.path.basename(epub_path))[0]
    logger = setup_logging(output_dir, epub_basename)
    
    # Register signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.warning(f"Received signal {signum}, shutting down...")
        logger.info(f"Processed chunks are saved in: {temp_dir}")
        sys.exit(1)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("=" * 70)
    logger.info("EPUB to M4B Audiobook Converter - Native Maya1 TTS")
    logger.info(f"Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"EPUB: {epub_path}")
    logger.info("=" * 70)
    
    # Voice description (audiobook narrator style)
    if voice is None:
        voice = "Male narrator voice in his 40s with an American accent. Warm baritone, calm pacing, clear diction, conversational delivery."
    
    logger.info(f"[CONFIG] Voice: {voice}")
    logger.info(f"[CONFIG] Output dir: {output_dir}")
    logger.debug(f"[CONFIG] Temp dir: {temp_dir}")
    
    # Initialize TTS engine
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"[CONFIG] Device: {device}")
    
    try:
        engine = Maya1TTSEngine(LOCAL_MODEL_DIR, device)
        engine.load()
        logger.info("[ENGINE] Model loaded successfully")
    except Exception as e:
        logger.error(f"[ENGINE] Failed to load model: {e}")
        logger.debug(traceback.format_exc())
        return None
    
    # Parse EPUB
    logger.info("-" * 70)
    logger.info("PARSING EPUB")
    logger.info("-" * 70)
    
    try:
        full_text, metadata = parse_epub(epub_path)
        logger.info(f"[EPUB] Title: {metadata.get('title', 'Unknown')}")
        logger.info(f"[EPUB] Author: {metadata.get('author', 'Unknown')}")
    except Exception as e:
        logger.error(f"[EPUB] Failed to parse: {e}")
        logger.debug(traceback.format_exc())
        return None
    
    # Clean and chunk text
    logger.info("[PROCESS] Cleaning text...")
    cleaned_text = clean_text(full_text)
    logger.info(f"[PROCESS] Cleaned text: {len(cleaned_text)} characters")
    
    logger.info("[PROCESS] Chunking text...")
    chunks = chunk_text_for_quality(cleaned_text, max_words=50, min_words=15)
    total_chunks = len(chunks)
    logger.info(f"[PROCESS] Created {total_chunks} chunks")
    
    # Estimate duration
    avg_chars = sum(len(c) for c in chunks) / total_chunks if total_chunks > 0 else 0
    estimated_duration = len(cleaned_text) / 15  # ~15 chars/second
    logger.info(f"[PROCESS] Estimated total duration: {estimated_duration/60:.1f} minutes")
    
    # Limit chunks if max_chunks is set
    if max_chunks is not None and max_chunks < total_chunks:
        logger.info(f"[PROCESS] Limiting to first {max_chunks} chunks (test mode)")
        chunks = chunks[:max_chunks]
        total_chunks = len(chunks)
    
    # Generate audio for each chunk
    logger.info("-" * 70)
    logger.info("GENERATING AUDIO")
    logger.info("-" * 70)
    
    audio_files = []
    failed_chunks = []
    total_audio_duration = 0
    start_time = time.time()
    
    for i, chunk in enumerate(chunks):
        chunk_num = i + 1
        word_count = len(chunk.split())
        
        logger.info(f"[CHUNK {chunk_num}/{total_chunks}] Words: {word_count}")
        logger.debug(f"  Text: {chunk[:150]}...")
        
        try:
            chunk_start = time.time()
            
            # Generate audio
            audio = engine.generate_audio(chunk, voice, max_duration_sec=60)
            
            if audio is not None and len(audio) > 0:
                duration = len(audio) / 24000
                total_audio_duration += duration
                
                # Save chunk
                chunk_path = os.path.join(temp_dir, f"chunk_{chunk_num:04d}.wav")
                sf.write(chunk_path, audio, 24000)
                audio_files.append(chunk_path)
                
                gen_time = time.time() - chunk_start
                logger.info(f"  ✓ Duration: {duration:.2f}s | Gen time: {gen_time:.2f}s | File: {os.path.basename(chunk_path)}")
            else:
                logger.warning(f"  ✗ Failed to generate audio for chunk {chunk_num}")
                failed_chunks.append(i)
                
        except Exception as e:
            logger.error(f"  ✗ Error on chunk {chunk_num}: {e}")
            logger.debug(traceback.format_exc())
            failed_chunks.append(i)
        
        # Progress update
        elapsed = time.time() - start_time
        avg_time_per_chunk = elapsed / chunk_num
        remaining = avg_time_per_chunk * (total_chunks - chunk_num)
        logger.info(f"  Progress: {chunk_num}/{total_chunks} ({100*chunk_num/total_chunks:.1f}%) | ETA: {remaining/60:.1f} min")
    
    # Summary of generation
    logger.info("-" * 70)
    logger.info("GENERATION SUMMARY")
    logger.info("-" * 70)
    logger.info(f"Successful chunks: {len(audio_files)}/{total_chunks}")
    logger.info(f"Failed chunks: {len(failed_chunks)}")
    logger.info(f"Total audio duration: {total_audio_duration/60:.2f} minutes")
    logger.info(f"Total generation time: {(time.time()-start_time)/60:.2f} minutes")
    
    if len(audio_files) == 0:
        logger.error("[ERROR] No audio generated!")
        return None
    
    # Stitch audio
    logger.info("-" * 70)
    logger.info("STITCHING AUDIO")
    logger.info("-" * 70)
    
    combined_wav = os.path.join(output_dir, "combined.wav")
    logger.info(f"[STITCH] Combining {len(audio_files)} chunks...")
    
    try:
        stitch_audio_files(audio_files, combined_wav, silence_ms=400)
        logger.info(f"[STITCH] Combined WAV: {combined_wav}")
    except Exception as e:
        logger.error(f"[STITCH] Failed to stitch audio: {e}")
        logger.debug(traceback.format_exc())
        return None
    
    # Export M4B
    logger.info("-" * 70)
    logger.info("EXPORTING M4B")
    logger.info("-" * 70)
    
    output_m4b = os.path.join(output_dir, f"{epub_basename}.m4b")
    
    try:
        export_m4b(combined_wav, output_m4b, metadata)
        logger.info(f"[M4B] Output: {output_m4b}")
    except Exception as e:
        logger.error(f"[M4B] Failed to export: {e}")
        logger.debug(traceback.format_exc())
        return None
    
    # Get final file size
    file_size_mb = os.path.getsize(output_m4b) / (1024 * 1024)
    logger.info(f"[M4B] Size: {file_size_mb:.2f} MB")
    
    # Cleanup temp files
    logger.info("[CLEANUP] Removing temp files...")
    for f in audio_files:
        try:
            os.remove(f)
        except OSError as e:
            print(f"[CLEANUP] Warning: Failed to remove {f}: {e}")
    try:
        os.remove(combined_wav)
        os.rmdir(temp_dir)
    except OSError as e:
        print(f"[CLEANUP] Warning: Failed to remove temp files: {e}")
    
    # Final summary
    logger.info("=" * 70)
    logger.info("CONVERSION COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Title: {metadata['title']}")
    logger.info(f"Author: {metadata['author']}")
    logger.info(f"Duration: {total_audio_duration/60:.2f} minutes")
    logger.info(f"Output: {output_m4b}")
    logger.info(f"Size: {file_size_mb:.2f} MB")
    logger.info("=" * 70)
    
    return output_m4b


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert EPUB to M4B audiobook using Maya1 TTS")
    parser.add_argument("epub", nargs="?", 
                        default="/mnt/Games/MBook/System Lost_ My Own Best Friend - DarkTechnomancer.epub",
                        help="Path to EPUB file")
    parser.add_argument("--test", type=int, default=None, metavar="N",
                        help="Test mode: only process first N chunks")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output directory")
    parser.add_argument("--voice", type=str, default=None,
                        help="Voice description for TTS")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.epub):
        print(f"Error: EPUB file not found: {args.epub}")
        sys.exit(1)
    
    result = convert_epub_to_audiobook(
        args.epub,
        output_dir=args.output,
        voice=args.voice,
        max_chunks=args.test
    )
    
    if result:
        print(f"\n✅ Audiobook saved to: {result}")
    else:
        print("\n❌ Conversion failed")
        sys.exit(1)
