"""
Chatterbox Turbo TTS Engine

Zero-shot voice cloning TTS engine using Chatterbox Turbo model.
Requires reference audio file (~10 seconds) for voice cloning.

Model: ResembleAI/chatterbox-turbo (350M parameters)
Output: 22.05 kHz WAV audio
Features: Native paralinguistic tags ([laugh], [cough], [chuckle])
"""

import os
import numpy as np


class ChatterboxTurboEngine:
    """Chatterbox Turbo TTS engine with voice cloning capability."""

    def __init__(self, device: str = "cuda"):
        """Initialize Chatterbox Turbo engine.

        Args:
            device: Device to run model on ("cuda" or "cpu")
        """
        self.device = device
        self.model = None
        self.sr = 22050  # 22.05kHz sample rate

    def load(self):
        """Load Chatterbox Turbo model from HuggingFace.

        Raises:
            ImportError: If chatterbox-tts package is not installed
            RuntimeError: If model loading fails
        """
        print("[ENGINE] Loading Chatterbox Turbo model...")

        try:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
        except ImportError as e:
            raise ImportError(
                "chatterbox-tts not installed.\n"
                "Install with: pip install chatterbox-tts"
            ) from e

        try:
            self.model = ChatterboxTurboTTS.from_pretrained(device=self.device)
            print(f"[ENGINE] Chatterbox Turbo loaded on {self.device}")
        except Exception as e:
            # Clean up any partially loaded resources
            self.cleanup()
            raise RuntimeError(f"Failed to load Chatterbox Turbo: {e}") from e

    def cleanup(self):
        """Clean up GPU/CPU resources.

        Releases model and clears CUDA cache if using GPU.
        """
        if hasattr(self, 'model') and self.model is not None:
            try:
                del self.model
                self.model = None
                print("[ENGINE] Chatterbox Turbo model released")
            except Exception as e:
                print(f"[ENGINE] Warning: Failed to release model: {e}")

        # Always attempt cleanup
        try:
            import gc
            gc.collect()

            if self.device == "cuda":
                import torch
                torch.cuda.empty_cache()
                print("[ENGINE] CUDA cache cleared")
        except Exception as e:
            print(f"[ENGINE] Warning: Failed to clear CUDA cache: {e}")

    def generate_audio(self, text: str, reference_audio_path: str,
                      max_duration_sec: float = 30.0) -> np.ndarray:
        """Generate audio using voice cloning.

        Args:
            text: Text to synthesize. Supports paralinguistic tags:
                  [laugh], [cough], [chuckle], etc.
            reference_audio_path: Path to reference WAV file (~10 seconds)
                                 for voice cloning
            max_duration_sec: Not used by Chatterbox (auto-determines length)

        Returns:
            Audio as numpy array (22.05kHz, mono, float32)

        Raises:
            FileNotFoundError: If reference audio file doesn't exist
            ValueError: If text is empty or reference audio is invalid
            RuntimeError: If audio generation fails
        """
        # Validate inputs
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        if not reference_audio_path:
            raise ValueError("Reference audio path is required")

        if not os.path.exists(reference_audio_path):
            raise FileNotFoundError(
                f"Reference audio not found: {reference_audio_path}\n"
                f"Please ensure voice samples are in the voice_samples/ directory"
            )

        if self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        try:
            # Generate audio with Chatterbox Turbo
            wav = self.model.generate(
                text,
                audio_prompt_path=reference_audio_path
            )

            # Convert torch tensor to numpy array
            if hasattr(wav, 'numpy'):
                audio = wav.numpy()
            elif hasattr(wav, 'cpu'):
                audio = wav.cpu().numpy()
            else:
                audio = np.array(wav)

            # Ensure 1D array (mono)
            if audio.ndim > 1:
                if audio.shape[0] == 1:
                    audio = audio[0]  # Remove channel dimension
                elif audio.shape[1] == 1:
                    audio = audio[:, 0]  # Transpose case
                else:
                    # Multiple channels - take first channel
                    audio = audio[0] if audio.shape[0] < audio.shape[1] else audio[:, 0]

            # Ensure float32 dtype
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            return audio

        except FileNotFoundError:
            # Re-raise file not found as-is
            raise
        except Exception as e:
            raise RuntimeError(
                f"Failed to generate audio with Chatterbox Turbo: {e}"
            ) from e

    def __del__(self):
        """Cleanup on garbage collection."""
        try:
            self.cleanup()
        except Exception:
            pass  # Ignore errors during cleanup in destructor


# Helper functions for reference audio validation

def validate_reference_audio(file_path: str) -> tuple[bool, str]:
    """Validate reference audio file format and quality.

    Args:
        file_path: Path to reference audio file

    Returns:
        (is_valid, error_message) - If valid, error_message is empty
    """
    if not os.path.exists(file_path):
        return False, f"File not found: {file_path}"

    if not file_path.lower().endswith('.wav'):
        return False, "Reference audio must be WAV format"

    try:
        import soundfile as sf

        # Check if file can be read
        data, samplerate = sf.read(file_path)

        # Check duration (should be 8-15 seconds)
        duration = len(data) / samplerate
        if duration < 5:
            return False, f"Audio too short ({duration:.1f}s). Need at least 5 seconds."
        if duration > 20:
            return False, f"Audio too long ({duration:.1f}s). Should be under 20 seconds."

        # Check channels (should be mono or stereo)
        if data.ndim > 2:
            return False, f"Too many audio channels ({data.ndim}). Use mono or stereo."

        return True, ""

    except Exception as e:
        return False, f"Invalid audio file: {e}"


def get_audio_info(file_path: str) -> dict:
    """Get information about reference audio file.

    Args:
        file_path: Path to audio file

    Returns:
        Dictionary with keys: duration, samplerate, channels, format
    """
    try:
        import soundfile as sf

        data, samplerate = sf.read(file_path)
        duration = len(data) / samplerate
        channels = 1 if data.ndim == 1 else data.shape[1]

        return {
            "duration": duration,
            "samplerate": samplerate,
            "channels": channels,
            "format": "WAV",
            "valid": True
        }
    except Exception as e:
        return {
            "duration": 0,
            "samplerate": 0,
            "channels": 0,
            "format": "unknown",
            "valid": False,
            "error": str(e)
        }
