# Voice Reference Samples for Chatterbox Turbo

These reference audio files are used for voice cloning with the Chatterbox Turbo TTS engine. Chatterbox Turbo uses zero-shot voice cloning to match the voice characteristics of the provided reference audio.

## Files

- **`en_us_male_warm.wav`** - American male narrator, warm tone (baritone)
- **`en_us_female_clear.wav`** - American female narrator, clear articulation
- **`en_gb_male_standard.wav`** - British male narrator, BBC-style

## Reference Audio Requirements

For best results, reference audio should meet these specifications:

- **Format**: WAV (uncompressed)
- **Duration**: 8-12 seconds (minimum 5s, maximum 20s)
- **Sample Rate**: 22.05 kHz or 24 kHz (Chatterbox will handle resampling)
- **Channels**: Mono preferred, stereo acceptable
- **Content**: Clean speech with natural prosody
  - No music or sound effects
  - Minimal background noise
  - Clear diction and consistent volume
  - Natural sentence flow (not just word lists)
- **Voice Quality**: Professional or semi-professional recording quality

## Usage in MBook

These samples are automatically used by the WebUI voice presets:
- **"EN-US CHATTERBOX (M)"** → `en_us_male_warm.wav`
- **"EN-US CHATTERBOX (F)"** → `en_us_female_clear.wav`
- **"EN-GB CHATTERBOX"** → `en_gb_male_standard.wav`

Custom reference audio can be provided via:
- The standalone testing GUI (`test_chatterbox_gui.py`)
- The main GUI (future feature)
- Direct API calls

## Obtaining Reference Audio

### Option 1: Generate with Helper Script (Quick Start)

Run the included helper script to generate basic reference samples:

```bash
python generate_voice_samples.py
```

This will create placeholder samples using edge-tts (free, high-quality). While these work, consider recording your own or using professional samples for best results.

### Option 2: Public Domain Sources (Recommended)

**LibriVox Audiobooks** - Professional narrators, public domain:
1. Visit [archive.org/details/librivoxaudio](https://archive.org/details/librivoxaudio)
2. Browse audiobooks and preview reader samples
3. Download MP3, extract clean 10-second clip
4. Convert to WAV using `ffmpeg`:
   ```bash
   ffmpeg -i input.mp3 -ar 22050 -ac 1 -t 10 -ss 30 output.wav
   ```
   - `-ar 22050`: Set sample rate to 22.05kHz
   - `-ac 1`: Convert to mono
   - `-t 10`: Duration 10 seconds
   - `-ss 30`: Start at 30 seconds (skip intro music)

**Common Voice Dataset** - Multi-speaker, validated recordings:
- Visit [commonvoice.mozilla.org](https://commonvoice.mozilla.org)
- Download validated clips for your target language/accent
- Select clips with high validation scores

### Option 3: Free TTS Services

Generate high-quality reference samples using online TTS:

**TTSMaker** ([ttsmaker.com](https://ttsmaker.com)):
- 100+ languages, 600+ voices
- Free commercial use
- Export as WAV format
- Recommended voices:
  - US Male: "en-US-GuyNeural" or "en-US-DavisNeural"
  - US Female: "en-US-JennyNeural" or "en-US-AriaNeural"
  - UK Male: "en-GB-RyanNeural" or "en-GB-LibbyNeural"

**Edge-TTS (Command Line)**:
```bash
# Install edge-tts
pip install edge-tts

# Generate US male sample
edge-tts --voice en-US-GuyNeural \
  --text "The art of narration requires clarity, warmth, and authentic expression. A skilled narrator brings stories to life with nuanced emotion and precise diction." \
  --write-media en_us_male_warm.wav

# Generate US female sample
edge-tts --voice en-US-JennyNeural \
  --text "Professional voice work demands attention to pacing, tone, and emotional range. Clear articulation and natural delivery are essential for engaging listeners." \
  --write-media en_us_female_clear.wav

# Generate UK male sample
edge-tts --voice en-GB-RyanNeural \
  --text "The British broadcasting tradition emphasizes measured pacing, refined pronunciation, and authoritative delivery. This classic style remains the gold standard for narration." \
  --write-media en_gb_male_standard.wav
```

Then convert to 22.05kHz mono:
```bash
ffmpeg -i en_us_male_warm.wav -ar 22050 -ac 1 en_us_male_warm_final.wav
```

### Option 4: Record Your Own

Use Audacity (free) to record custom reference audio:
1. Record 10-15 seconds of natural speech
2. Remove noise using Effect → Noise Reduction
3. Normalize volume to -3dB
4. Export as WAV, 22050 Hz, mono

**Sample Text Suggestions**:
- "The art of storytelling has captivated humanity for centuries. Through vivid description and emotional resonance, narrators bring tales to life, transporting listeners to distant worlds and forgotten times."
- "Professional voice work requires careful attention to pacing, tone, and emotional authenticity. Clear articulation and natural delivery are essential for engaging an audience."

## Testing Reference Audio Quality

Use the testing GUI to validate your reference samples:

```bash
python test_chatterbox_gui.py
```

Good indicators:
- Generated audio matches the reference voice timbre
- Pronunciation and accent are preserved
- Prosody feels natural, not robotic

Poor indicators:
- Generated audio sounds significantly different from reference
- Accent/pronunciation drifts
- Audio has artifacts or glitches

## License & Attribution

When using reference audio from external sources:
- **LibriVox**: Public domain, no attribution required
- **Common Voice**: CC0 license, attribution appreciated
- **TTS Services**: Check service terms (most allow commercial use)
- **Personal Recordings**: Ensure you have rights to use the voice

## Replacing Default Samples

To replace the default samples:
1. Create your new WAV file following the specifications above
2. Name it according to the preset you want to replace
3. Place it in this `voice_samples/` directory
4. Restart the MBook application
5. Test using the testing GUI before running full conversions

## Troubleshooting

**"Reference audio not found" error**:
- Ensure WAV files are in `/mnt/Games/MBook/voice_samples/`
- Check file names match exactly (case-sensitive)

**Generated audio doesn't match reference voice**:
- Reference clip may be too short (< 8 seconds)
- Reference audio has background noise
- Reference has multiple speakers or music
- Try a cleaner reference clip

**Poor audio quality in generated speech**:
- Check reference audio sample rate (should be 22.05kHz or higher)
- Ensure reference is high quality (not compressed/artifacts)
- Verify reference has consistent volume

**Accent/pronunciation issues**:
- Reference audio language must match target language
- Chatterbox works best with clear, native speakers
- Avoid heavy accents if you want neutral output

## Additional Resources

- [Chatterbox Turbo Demo Page](https://resemble-ai.github.io/chatterbox_turbo_demopage/)
- [Chatterbox GitHub](https://github.com/resemble-ai/chatterbox)
- [HuggingFace Model Card](https://huggingface.co/ResembleAI/chatterbox-turbo)
- [MBook Documentation](../README.md)
