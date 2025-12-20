import os
import glob
from typing import Dict, List, Optional

DEFAULT_VOICE_PROMPT = (
    "Male narrator voice in his 40s with an American accent. "
    "Warm baritone, calm pacing, clear diction, conversational delivery."
)

VOICE_PRESETS: List[Dict[str, str]] = [
    # Maya1 presets (natural language voice descriptions)
    {
        "id": "male_us_warm",
        "label": "EN-US NEURAL (M)",
        "engine": "maya1",
        "prompt": DEFAULT_VOICE_PROMPT,
    },
    {
        "id": "female_us_clear",
        "label": "EN-US NEURAL (F)",
        "engine": "maya1",
        "prompt": "Female narrator voice in her 30s with an American accent. Professional, clear articulation, warm and engaging tone.",
    },
    {
        "id": "male_uk_classic",
        "label": "EN-GB STANDARD",
        "engine": "maya1",
        "prompt": "Male narrator voice with a British accent in his 40s. Classic BBC style, authoritative and refined tone, measured pacing.",
    },
    # Chatterbox Turbo presets (voice cloning via reference audio)
    {
        "id": "chatterbox_male_us",
        "label": "EN-US CHATTERBOX (M)",
        "engine": "chatterbox",
        "reference_audio": "voice_samples/en_us_male_warm.wav",
    },
    {
        "id": "chatterbox_female_us",
        "label": "EN-US CHATTERBOX (F)",
        "engine": "chatterbox",
        "reference_audio": "voice_samples/en_us_female_clear.wav",
    },
    {
        "id": "chatterbox_male_gb",
        "label": "EN-GB CHATTERBOX",
        "engine": "chatterbox",
        "reference_audio": "voice_samples/en_gb_male_standard.wav",
    },
    # Custom narrator voices
    {
        "id": "chatterbox_ks",
        "label": "KAREN SAVAGE (F)",
        "engine": "chatterbox",
        "reference_audio": "voice_samples/KS_FEMALE_22k.wav",
    },
    {
        "id": "chatterbox_sj",
        "label": "SCARLETT J (F)",
        "engine": "chatterbox",
        "reference_audio": "voice_samples/SJ_FEMALE_22k.wav",
    },
]


def get_voice_preset(voice_id: str) -> Dict[str, str]:
    """Return voice preset configuration by ID."""
    preset = next((p for p in VOICE_PRESETS if p["id"] == voice_id), None)
    if not preset:
        # Fallback if ID not found (might have changed engine filters)
        # Try to find any preset, or just raise error
        raise ValueError(f"Unknown voice preset: {voice_id}")
    return preset


def get_voice_presets(engine_filter: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Return voice presets, optionally filtered by engine.

    Args:
        engine_filter: 'maya1' or 'chatterbox'. If None, returns all.
    """
    if not engine_filter:
        return VOICE_PRESETS

    return [p for p in VOICE_PRESETS if p.get("engine") == engine_filter]


def get_voice_samples_dir() -> str:
    """Return absolute path to voice samples directory."""
    # Assuming voice_samples is in root relative to this file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "voice_samples")


def get_available_voice_samples() -> List[str]:
    """Return list of .wav files in voice_samples directory."""
    samples_dir = get_voice_samples_dir()
    if not os.path.exists(samples_dir):
        return []

    files = glob.glob(os.path.join(samples_dir, "*.wav"))
    return sorted([os.path.basename(f) for f in files])


def validate_voice_preset(voice_id: str) -> Dict[str, str]:
    """Validate voice preset configuration and resources."""
    preset = get_voice_preset(voice_id)

    if preset.get("engine") == "chatterbox":
        ref_path = preset.get("reference_audio")
        if not ref_path:
            raise ValueError(f"Chatterbox preset {voice_id} missing reference_audio field")
        if not os.path.exists(ref_path):
            raise FileNotFoundError(
                f"Reference audio missing: {ref_path}\n"
                f"Please ensure voice samples are in voice_samples/ directory.\n"
                f"Run: python generate_voice_samples.py"
            )

    return preset
