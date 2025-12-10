# MBook - Maya1 Audiobook Generator

Convert EPUB files to high-quality M4B audiobooks using Maya1's native text-to-speech with SNAC neural codec.

## Features

- **Native Maya1 TTS** - Uses the 3B-parameter Maya1 model for natural speech synthesis
- **SNAC Neural Codec** - 24kHz audio output with excellent quality
- **Voice Customization** - Natural language voice descriptions (age, accent, tone, pacing)
- **EPUB Support** - Parses EPUB files and extracts text automatically
- **M4B Export** - Creates audiobook files with metadata (title, author)
- **Progress Logging** - Persistent log files for long-running conversions
- **Graceful Interruption** - Can resume from saved chunks if interrupted

## Requirements

- Python 3.10+
- CUDA-capable GPU with 8GB+ VRAM (16GB+ recommended)
- ffmpeg installed on system

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/MBook.git
cd MBook

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: .\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Download spacy model
python -m spacy download en_core_web_sm

# Download Maya1 model (first run will download ~6.6GB)
python -c "from transformers import AutoModelForCausalLM; AutoModelForCausalLM.from_pretrained('maya-research/maya1')"
```

## Usage

### Command Line

```bash
# Convert an EPUB to M4B
python convert_epub_to_audiobook.py "Book Title.epub"

# Test mode (first N chunks only)
python convert_epub_to_audiobook.py "Book Title.epub" --test 10

# Custom voice
python convert_epub_to_audiobook.py "Book Title.epub" \
  --voice "Female narrator in her 20s with an American accent. Warm, clear, expressive tone."

# Custom output directory
python convert_epub_to_audiobook.py "Book Title.epub" -o /path/to/output
```

### GUI Application

```bash
python main.py
```

## Voice Descriptions

Maya1 uses natural language voice descriptions. Examples:

```
# Professional audiobook narrator
Male narrator voice in his 40s with an American accent. Warm baritone, calm pacing, clear diction.

# Young female narrator
Female voice in her 20s with a British accent. Light, energetic, conversational delivery.

# Character voices
Dark villain character. Male voice in their 40s with a British accent. Low pitch, gravelly timbre, slow pacing.
```

### Supported Voice Attributes

- **Age**: 20s, 30s, 40s
- **Gender**: Male, Female
- **Accent**: American, British, Australian, etc.
- **Timbre**: Warm, gravelly, robotic, ethereal
- **Pacing**: very_slow, slow, conversational, brisk, fast, very_fast
- **Emotion**: neutral, energetic, excited, sad, sarcastic, dry

## Project Structure

```
MBook/
├── convert_epub_to_audiobook.py  # Main converter script
├── pipeline.py                   # Maya1 pipeline wrapper
├── assembler.py                  # Audio stitching utilities
├── main.py                       # GUI application
├── requirements.txt              # Python dependencies
├── models/                       # Downloaded Maya1 model files
└── audiobook_output/             # Generated audiobooks
```

## Performance

- **Generation Speed**: ~2x realtime (30 seconds of audio in 60 seconds)
- **Quality**: Near-perfect duration accuracy for chunks of 40-60 words
- **Memory**: ~6GB GPU VRAM for model, peaks at ~10GB during generation

## Speed Optimization (Future)

For faster generation, consider using **vLLM** which provides:
- **Automatic Prefix Caching** - Caches voice description for faster subsequent chunks
- **Continuous Batching** - Process multiple chunks in parallel
- **Sub-100ms streaming latency**

See `models/maya1/vllm_streaming_inference.py` for the vLLM implementation.

```bash
# Install vLLM (optional, for faster inference)
pip install vllm
```

## Logging

All conversions create a log file in the output directory:
```
audiobook_output/conversion_BookName_20251210_120000.log
```

Logs include timestamps, chunk progress, and any errors for debugging.

## License

MIT License - See LICENSE file for details.

## Credits

- **Maya1 Model**: [maya-research/maya1](https://huggingface.co/maya-research/maya1) - Apache 2.0
- **SNAC Codec**: [hubertsiuzdak/snac_24khz](https://huggingface.co/hubertsiuzdak/snac_24khz)
