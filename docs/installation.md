# Installation

This guide covers the installation of ttsforge and its dependencies.

## System Requirements

- **Python**: 3.10 or later
- **Operating System**: Linux, macOS, or Windows
- **Disk Space**: ~330MB for ONNX models (downloaded automatically on first use)

## Dependencies

ttsforge requires the following external tools:

### PyKokoro memory API

The package requires PyKokoro `>=0.7.5,<0.8`. This release provides the public
memory-ownership API used by TTSForge to disable retained segment audio and release
completed chapter results. Whole chapters are still synthesized into a buffered WAV;
streaming is not part of this integration.

### ffmpeg (Required for MP3/FLAC/OPUS/M4B)

ffmpeg is required for MP3/FLAC/OPUS/M4B output and chapter merging.

**Termux (Android):**

```bash
pkg install ffmpeg
```

**Ubuntu/Debian:**

```bash
sudo apt-get install ffmpeg
```

**macOS (Homebrew):**

```bash
brew install ffmpeg
```

**Windows:**

Download from <https://ffmpeg.org/download.html> and add it to `PATH`.

### Optional: bundled ffmpeg via Python (not available on all platforms)

If you cannot install a system ffmpeg, you can try the optional prebuilt binaries:

```bash
pip install "ttsforge[static_ffmpeg]"
```

### espeak-ng (Required for Phonemization)

espeak-ng is used for text-to-phoneme conversion.

**Ubuntu/Debian:**

```bash
sudo apt-get install espeak-ng
```

**macOS (Homebrew):**

```bash
brew install espeak-ng
```

**Windows:**

Download from <https://github.com/espeak-ng/espeak-ng/releases>

### Audio Playback (Optional)

Audio playback features (`--play` flags and the `read` command) require `sounddevice`:

```bash
pip install "ttsforge[audio]"
```

Or install directly:

```bash
pip install sounddevice
```

### spaCy Models (Optional)

spaCy is used for sentence splitting, name extraction, and spaCy-aware phonemization
workflows:

```bash
pip install spacy
python -m spacy download en_core_web_sm
python -m spacy download en_core_web_md
```

## Installing ttsforge

### From PyPI (Recommended)

```bash
pip install ttsforge
```

The base installation includes the CPU ONNX Runtime provider. Provider-dependent modules
are loaded only when audio rendering starts, so `import ttsforge`, `ttsforge --help`,
and configuration/inspection commands work without model initialization.

Optional extras:

```bash
# Audio playback (required for --play and read)
pip install "ttsforge[audio]"

# Bundled ffmpeg binaries
pip install "ttsforge[static_ffmpeg]"

# GPU acceleration
pip install "ttsforge[gpu]"
```

### From Source

```bash
git clone https://github.com/buchwandler/ttsforge.git
cd ttsforge
pip install -e .
```

### Development Installation

For development with testing and linting tools:

```bash
git clone https://github.com/buchwandler/ttsforge.git
cd ttsforge
pip install -e ".[dev]"
```

## ONNX Runtime Providers

Select a provider with an alias or full runtime provider name. The legacy Boolean
interface remains available for compatibility, but NNAPI and XNNPACK are execution
providers rather than GPU modes:

```bash
ttsforge config --set onnx_provider cpu
ttsforge sample "Provider test" --provider xnnpack
```

For CUDA, install the GPU extra in a fresh environment so CPU and GPU ONNX Runtime
distributions are not installed together:

```bash
pip install "ttsforge[gpu]"
ttsforge config --set onnx_provider cuda
```

For Termux/Android with PyKokoro v0.7.5 and an ONNX Runtime build exposing NNAPI or
XNNPACK:

```bash
ttsforge config --set model_source github --set onnx_provider nnapi
ttsforge config --show
ttsforge sample "Termux provider test" --provider nnapi
```

Use `--gpu` as a compatibility shortcut for `--provider auto` or `--no-gpu` for
`--provider cpu`. Provider availability and the documented `ONNX_PROVIDER` environment
override are handled by PyKokoro.

## Memory diagnostics

Set `TTSFORGE_MEMORY_DEBUG=1` to log RSS, peak RSS, available memory, and the effective
ONNX provider before and after runner initialization, chapter synthesis, WAV writing,
result release, state saves, final merging, and converter cleanup. Native allocators may
retain pages at a high-water mark after audio release; this diagnostic does not claim a
provider-native leak from RSS alone.

## Mixed-Language Support (Optional)

For automatic detection and handling of multiple languages in text (e.g., German text
with English technical terms):

```bash
pip install lingua-language-detector
```

Then enable mixed-language mode:

```bash
ttsforge config --set use_mixed_language true
ttsforge config --set mixed_language_primary de
ttsforge config --set mixed_language_allowed "['de', 'en-us']"
```

Or use the `--use-mixed-language` flag with commands:

```bash
ttsforge convert book.epub \
    --use-mixed-language \
    --mixed-language-primary de \
    --mixed-language-allowed de,en-us
```

## Downloading Models

ttsforge uses Kokoro ONNX models (~330MB total) which are downloaded automatically on
first use. You can also download them proactively:

```bash
# Download models
ttsforge download

# Force re-download
ttsforge download --force
```

Models are stored in:

- Linux: `~/.cache/ttsforge/`
- macOS: `~/Library/Caches/ttsforge/`
- Windows: `%LOCALAPPDATA%\ttsforge\Cache\`

## Verifying Installation

Verify that ttsforge is installed correctly:

```bash
# Check version
ttsforge --version

# Show current configuration
ttsforge config --show

# Generate a sample audio file
ttsforge sample "Hello, world!"
```

If the sample command succeeds and creates `sample.wav`, ttsforge is ready to use.

## Troubleshooting

### ffmpeg not found

If you see "ffmpeg not found" errors when creating M4B files:

1. Ensure ffmpeg is installed (see above)
2. Verify it's in your PATH: `ffmpeg -version`
3. On Windows, you may need to restart your terminal after installation

### espeak-ng not found

If phonemization fails:

1. Ensure espeak-ng is installed (see above)
2. On Linux, the library should be `libespeak-ng.so.1`
3. On macOS with Homebrew, it's typically at `/opt/homebrew/lib/libespeak-ng.dylib`

### Model download fails

If model download fails:

1. Check your internet connection
2. Try downloading manually with `ttsforge download`
3. Check disk space (~330MB required)
4. The model directory can be found with `ttsforge config --show`

### GPU not detected

If GPU acceleration isn't working:

1. Ensure `onnxruntime-gpu` is installed (not just `onnxruntime`)
2. Verify CUDA is properly installed
3. Check GPU compatibility with ONNX Runtime
