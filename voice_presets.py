import os
from typing import Dict, List

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
        raise ValueError(f"Unknown voice preset: {voice_id}")
    return preset


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
