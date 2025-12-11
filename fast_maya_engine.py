"""
FastMaya1 TTS Engine - Batch Processing with LMDeploy

This module provides an alternative TTS engine using lmdeploy for faster inference.
It is designed to be used alongside (not replace) the existing Maya1TTSEngine.

Key features:
- Uses lmdeploy TurbomindEngine for optimized LLM inference
- Supports batch processing (multiple chunks at once)
- Optional 48kHz upsampling via FastAudioSR for improved quality
- Prefix caching and KV-cache quantization for memory efficiency

Dependencies (optional - only needed if using this engine):
- lmdeploy
- FastAudioSR (for upsampling)

Usage:
    from fast_maya_engine import FastMaya1Engine, is_lmdeploy_available
    
    if is_lmdeploy_available():
        engine = FastMaya1Engine(memory_util=0.5, use_upsampler=True)
        engine.load()
        
        # Single chunk (compatible with Maya1TTSEngine interface)
        audio = engine.generate_audio(text, voice_description)
        
        # Batch processing (multiple chunks at once)
        audios = engine.batch_generate(texts, voice_description)
"""

import os
import numpy as np
from typing import List, Optional, Union

# Check for lmdeploy availability
def is_lmdeploy_available() -> bool:
    """Check if lmdeploy is installed and available."""
    try:
        import lmdeploy
        return True
    except ImportError:
        return False

def is_fasr_available() -> bool:
    """Check if FastAudioSR upsampler is installed."""
    try:
        from FastAudioSR import FASR
        return True
    except ImportError:
        return False


# Token constants (same as existing Maya1 implementation)
CODE_START_TOKEN_ID = 128257
CODE_END_TOKEN_ID = 128258
CODE_TOKEN_OFFSET = 128266
SNAC_MIN_ID = 128266
SNAC_MAX_ID = 156937
SNAC_TOKENS_PER_FRAME = 7


class FastMaya1Engine:
    """
    Fast Maya1 TTS engine using lmdeploy for optimized inference.
    
    This engine provides significant speed improvements over the transformers-based
    Maya1TTSEngine, especially when using batch processing.
    
    Args:
        memory_util: Fraction of GPU memory to use (0.0 to 1.0). Default: 0.5
        tp: Tensor parallel size (number of GPUs). Default: 1
        use_upsampler: Whether to use AudioSR for 48kHz upsampling. Default: True
        enable_prefix_caching: Enable prefix caching for batching. Default: True
        quant_policy: KV cache quantization (8 for 8-bit, 0 for none). Default: 8
    """
    
    # Output sample rate
    BASE_SAMPLE_RATE = 24000
    UPSAMPLED_RATE = 48000
    
    def __init__(
        self,
        memory_util: float = 0.5,
        tp: int = 1,
        use_upsampler: bool = True,
        enable_prefix_caching: bool = True,
        quant_policy: int = 8
    ):
        self.memory_util = memory_util
        self.tp = tp
        self.use_upsampler = use_upsampler
        self.enable_prefix_caching = enable_prefix_caching
        self.quant_policy = quant_policy
        
        # Models (loaded lazily)
        self.pipe = None
        self.snac_model = None
        self.upsampler = None
        self.gen_config = None
        
        # Track loaded state
        self._loaded = False
        
    @property
    def sample_rate(self) -> int:
        """Return the output sample rate based on upsampler setting."""
        return self.UPSAMPLED_RATE if self.use_upsampler else self.BASE_SAMPLE_RATE
    
    def load(self):
        """Load all models."""
        if self._loaded:
            return
            
        import torch
        
        # Validate lmdeploy is available
        if not is_lmdeploy_available():
            raise ImportError(
                "lmdeploy is not installed. Install it with:\n"
                "  pip install lmdeploy\n"
                "Or use Maya1TTSEngine instead for standard inference."
            )
        
        from lmdeploy import pipeline, TurbomindEngineConfig, GenerationConfig
        from snac import SNAC
        import warnings

        print("[FastMaya] Loading lmdeploy pipeline...")

        try:
            # Configure backend
            backend_config = TurbomindEngineConfig(
                cache_max_entry_count=self.memory_util,
                tp=self.tp,
                enable_prefix_caching=self.enable_prefix_caching,
                quant_policy=self.quant_policy
            )

            # Load the pipeline
            # SECURITY WARNING: lmdeploy pipeline internally uses trust_remote_code=True
            # for custom model architectures. Only use with trusted models.
            warnings.warn(
                "Loading model with lmdeploy pipeline which internally uses trust_remote_code=True. "
                "This allows arbitrary code execution from the model repository. "
                "Only use with trusted sources like maya-research/maya1.",
                RuntimeWarning,
                stacklevel=2
            )
            self.pipe = pipeline("maya-research/maya1", backend_config=backend_config)
            print("[FastMaya] Pipeline loaded")

            # Load SNAC decoder
            print("[FastMaya] Loading SNAC decoder...")
            self.snac_model = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval().to("cuda")
            print("[FastMaya] SNAC loaded")

            # Load upsampler if requested
            if self.use_upsampler:
                if is_fasr_available():
                    from FastAudioSR import FASR
                    from huggingface_hub import snapshot_download

                    print("[FastMaya] Loading AudioSR upsampler...")
                    upsampler_path = snapshot_download("YatharthS/FlashSR")
                    self.upsampler = FASR(f"{upsampler_path}/upsampler.pth")
                    _ = self.upsampler.model.half()
                    print("[FastMaya] Upsampler loaded (48kHz output)")
                else:
                    print("[FastMaya] Warning: FastAudioSR not installed. Using 24kHz output.")
                    self.use_upsampler = False
        except Exception as e:
            # Clean up any partially loaded models
            self.cleanup()
            raise RuntimeError(f"Failed to load models: {e}") from e

    def cleanup(self):
        """Clean up GPU/CPU resources."""
        import torch
        # Clean each resource independently to prevent one failure from blocking others
        if hasattr(self, 'pipe') and self.pipe is not None:
            try:
                del self.pipe
                self.pipe = None
                print("[FastMaya] Pipeline released")
            except Exception as e:
                print(f"[FastMaya] Warning: Failed to release pipeline: {e}")

        if hasattr(self, 'snac_model') and self.snac_model is not None:
            try:
                del self.snac_model
                self.snac_model = None
                print("[FastMaya] SNAC model released")
            except Exception as e:
                print(f"[FastMaya] Warning: Failed to release SNAC model: {e}")

        if hasattr(self, 'upsampler') and self.upsampler is not None:
            try:
                del self.upsampler
                self.upsampler = None
                print("[FastMaya] Upsampler released")
            except Exception as e:
                print(f"[FastMaya] Warning: Failed to release upsampler: {e}")

        # Always attempt cleanup, regardless of failures above
        try:
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            print("[FastMaya] CUDA cache cleared")
        except Exception as e:
            print(f"[FastMaya] Warning: Failed to clear CUDA cache: {e}")
        
        # Generation config
        self.gen_config = GenerationConfig(
            top_p=0.9,
            top_k=40,
            temperature=0.4,
            max_new_tokens=1024,
            repetition_penalty=1.4,
            stop_token_ids=[CODE_END_TOKEN_ID],
            do_sample=True,
            min_p=0.0
        )
        
        self._loaded = True
        print("[FastMaya] Engine ready")
    
    def _format_prompt(self, text: str, voice: str) -> str:
        """Format the prompt for Maya1."""
        return f'<custom_token_3><|begin_of_text|><description="{voice}"> {text}<|eot_id|><custom_token_4><custom_token_5><custom_token_1>'
    
    def _extract_snac_codes(self, token_ids: list) -> list:
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
    
    def _decode_audio(self, token_ids: list) -> np.ndarray:
        """Decode SNAC tokens to audio waveform."""
        import torch
        import librosa
        
        snac_tokens = self._extract_snac_codes(token_ids)
        levels = self._unpack_snac(snac_tokens)
        
        if not levels[0]:  # Empty audio
            return np.array([], dtype=np.float32)
        
        device = 'cuda'
        codes_tensor = [
            torch.tensor(level, dtype=torch.long, device=device).unsqueeze(0)
            for level in levels
        ]
        
        with torch.inference_mode():
            z_q = self.snac_model.quantizer.from_codes(codes_tensor)
            audio = self.snac_model.decoder(z_q)[0, 0].cpu().numpy()
            
            # Upsample if enabled
            if self.use_upsampler and self.upsampler is not None:
                audio16k = librosa.resample(y=audio, orig_sr=24000, target_sr=16000, res_type='soxr_hq')
                audio16k = torch.from_numpy(audio16k).unsqueeze(0).to("cuda").half()
                audio = self.upsampler.run(audio16k).cpu().numpy()
        
        return audio
    
    def generate_audio(
        self,
        text: str,
        voice_description: str,
        max_duration_sec: float = 60.0
    ) -> np.ndarray:
        """
        Generate audio for a single text chunk.

        This method provides interface compatibility with Maya1TTSEngine.

        Args:
            text: Text to synthesize
            voice_description: Voice description for the narrator
            max_duration_sec: Maximum duration (used to set max_new_tokens)

        Returns:
            Audio waveform as numpy array
        """
        # Validate voice_description
        if not voice_description or not voice_description.strip():
            raise ValueError("voice_description cannot be empty")
        if len(voice_description) > 1000:
            raise ValueError(f"voice_description too long ({len(voice_description)} chars, max 1000)")

        if not self._loaded:
            self.load()
        
        # Adjust max tokens for longer audio
        expected_frames = int(max_duration_sec * 47)
        self.gen_config.max_new_tokens = max(expected_frames * 7, 1024)
        
        formatted_prompt = self._format_prompt(text, voice_description)
        responses = self.pipe([formatted_prompt], gen_config=self.gen_config, do_preprocess=False)
        
        if not responses or not responses[0].token_ids:
            return None
        
        audio = self._decode_audio(responses[0].token_ids)
        return audio
    
    def batch_generate(
        self,
        texts: List[str],
        voice_description: Union[str, List[str]],
        max_duration_sec: float = 60.0,
        return_concatenated: bool = False
    ) -> Union[List[np.ndarray], np.ndarray]:
        """
        Generate audio for multiple text chunks in a single batch.
        
        This is the key speed improvement over sequential generation.
        
        Args:
            texts: List of text chunks to synthesize
            voice_description: Voice description (single string for all, or list per chunk)
            max_duration_sec: Maximum duration per chunk
            return_concatenated: If True, return single concatenated array. 
                                 If False (default), return list of individual arrays.
        
        Returns:
            List of audio arrays (one per chunk) or single concatenated array
        """
        if not self._loaded:
            self.load()
        
        if len(texts) == 0:
            return [] if not return_concatenated else np.array([], dtype=np.float32)
        
        # Handle voice descriptions
        if isinstance(voice_description, str):
            voices = [voice_description] * len(texts)
        else:
            voices = voice_description
        
        if len(voices) != len(texts):
            raise ValueError(f"Number of voices ({len(voices)}) must match number of texts ({len(texts)})")
        
        # Adjust max tokens for longer audio
        expected_frames = int(max_duration_sec * 47)
        self.gen_config.max_new_tokens = max(expected_frames * 7, 1024)
        
        # Format all prompts
        formatted_prompts = [
            self._format_prompt(text, voice)
            for text, voice in zip(texts, voices)
        ]
        
        # Generate all at once
        print(f"[FastMaya] Batch generating {len(texts)} chunks...")
        responses = self.pipe(formatted_prompts, gen_config=self.gen_config, do_preprocess=False)
        
        # Decode each response
        audios = []
        for i, response in enumerate(responses):
            if response.token_ids:
                audio = self._decode_audio(response.token_ids)
                audios.append(audio)
            else:
                print(f"[FastMaya] Warning: Empty response for chunk {i}")
                audios.append(np.array([], dtype=np.float32))
        
        if return_concatenated:
            # Filter out empty arrays and concatenate
            valid_audios = [a for a in audios if len(a) > 0]
            if valid_audios:
                return np.concatenate(valid_audios)
            return np.array([], dtype=np.float32)
        
        return audios
