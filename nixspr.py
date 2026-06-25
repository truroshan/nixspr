#!/usr/bin/env python3
import os
import sys
import time
import signal
import subprocess
import wave
import argparse
import logging
from pathlib import Path

import torch
import torchaudio
from google import genai

PID_FILE = Path("/tmp/nixspr.pid")
AUDIO_FILE = Path("/tmp/nixspr.wav")
STOP_PID_FILE = Path("/tmp/nixspr-stop.pid")
DEFAULT_MODEL = "gemini-2.5-flash"

# Read version from file
VERSION_FILE = Path(__file__).parent / ".version"
try:
    VERSION = VERSION_FILE.read_text().strip()
except Exception:
    VERSION = "unknown"

# Setup logging
logger = logging.getLogger("nixspr")


def notify(msg, error=False):
    """Send desktop notification."""
    title = "Nixspr"
    urgency = "critical" if error else "normal"
    subprocess.run(
        ["notify-send", "-u", urgency, title, msg],
        stderr=subprocess.DEVNULL
    )

    if error:
        logger.error(msg)
    else:
        logger.info(msg)


def cancel_operation():
    """Cancel any ongoing recording or transcription."""
    logger.debug("Cancelling operation")

    # Kill recording process
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            logger.debug(f"Stopping recording process (PID: {pid})")
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, ValueError) as e:
            logger.debug(f"Recording process not found: {e}")
        PID_FILE.unlink(missing_ok=True)

    # Kill transcription process
    if STOP_PID_FILE.exists():
        try:
            pid = int(STOP_PID_FILE.read_text().strip())
            logger.debug(f"Stopping transcription process (PID: {pid})")
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, ValueError) as e:
            logger.debug(f"Transcription process not found: {e}")
        STOP_PID_FILE.unlink(missing_ok=True)

    # Clean up audio file
    AUDIO_FILE.unlink(missing_ok=True)
    logger.debug("Cleanup complete")
    notify("Operation cancelled")


def start_recording():
    """Start audio recording from default pulse source."""
    logger.debug("Starting recording")

    # Cancel any ongoing operation first
    if PID_FILE.exists() or STOP_PID_FILE.exists():
        logger.debug("Existing operation found, cancelling")
        cancel_operation()

    # Delete old audio file if it exists
    if AUDIO_FILE.exists():
        AUDIO_FILE.unlink()
        logger.debug("Deleted previous audio file")

    logger.debug("Starting audio capture")
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-f", "pulse",
            "-i", "default",
            "-ac", "1",
            "-ar", "16000",
            str(AUDIO_FILE),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    PID_FILE.write_text(str(proc.pid))
    logger.info(f"Recording started (PID: {proc.pid})")
    notify("Recording started")


def transcribe_audio(api_key=None, model=None):
    """Transcribe audio file using Gemini API."""
    if not api_key:
        api_key = os.environ.get("NIXSPR_GEMINI_API_KEY")

    if not api_key:
        logger.error("API key not configured")
        notify("API key not configured. Please set NIXSPR_GEMINI_API_KEY.", error=True)
        return ""

    if not model:
        model = os.environ.get("NIXSPR_GEMINI_MODEL", DEFAULT_MODEL)

    logger.debug(f"Using model: {model}")
    logger.debug(f"Audio file size: {AUDIO_FILE.stat().st_size} bytes")

    client = genai.Client(api_key=api_key)

    # Read audio file
    with open(AUDIO_FILE, "rb") as f:
        audio_data = f.read()

    # Generate transcription
    prompt = (
        "Transcribe exactly what was spoken with natural punctuation. "
        "IMPORTANT: Use ONLY Roman/Latin script. NEVER use Devanagari or any other script. "
        "For Hindi words, write them in Roman script (Hinglish transliteration). "
        "Remove filler words (um, uh, like) and repetitions. "
        "If list items are detected, format as compact bullet points with single line breaks. "
        "When formatting bullets, strip redundant list markers (First/Second/Item one/Item two/etc) and keep only the actual content. "
        "Use a single blank line only when topic/context changes significantly. "
        "Return only the transcript, nothing else."
    )

    logger.debug("Sending audio to transcription service")
    response = client.models.generate_content(
        model=model,
        contents=[
            genai.types.Part.from_bytes(
                data=audio_data,
                mime_type="audio/wav"
            ),
            prompt
        ]
    )

    text = response.text.strip()
    logger.debug(f"Transcription received: {len(text)} characters")
    return text


def get_audio_duration(file_path):
    """Get audio file duration in seconds using wave module."""
    try:
        with wave.open(str(file_path), 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        return 0


def remove_silence_vad(audio_file):
    """Remove silence from audio using Silero VAD and return speech duration."""
    logger.debug("Loading voice activity detection model")
    model_path = os.environ.get("NIXSPR_VAD_MODEL_PATH")
    model, utils = torch.hub.load(repo_or_dir=model_path, model='silero_vad', source='local', force_reload=False, onnx=False)
    (get_speech_timestamps, _, _, _, collect_chunks) = utils

    logger.debug(f"Reading audio file: {audio_file}")
    wav, sr = torchaudio.load(str(audio_file))

    # Convert to mono if stereo
    if wav.shape[0] > 1:
        logger.debug("Converting stereo to mono")
        wav = torch.mean(wav, dim=0, keepdim=True)

    # Resample to 16000 Hz if needed
    if sr != 16000:
        logger.debug(f"Resampling from {sr}Hz to 16000Hz")
        resampler = torchaudio.transforms.Resample(sr, 16000)
        wav = resampler(wav)

    wav = wav.squeeze()

    logger.debug("Detecting speech segments")
    speech_timestamps = get_speech_timestamps(wav, model, sampling_rate=16000)

    if not speech_timestamps:
        logger.info("No speech detected in audio")
        return 0

    logger.debug(f"Found {len(speech_timestamps)} speech segments")
    speech_audio = collect_chunks(speech_timestamps, wav)

    # Save processed audio
    torchaudio.save(str(audio_file), speech_audio.unsqueeze(0), 16000)

    speech_duration = len(speech_audio) / 16000.0
    logger.info(f"Speech duration after silence removal: {speech_duration:.1f}s")

    return speech_duration


def paste_text(text):
    """Paste text via clipboard, preserving existing clipboard content."""
    logger.debug("Saving current clipboard")
    try:
        old_clipboard = subprocess.run(
            ["wl-paste"],
            capture_output=True,
            text=True,
            check=False
        ).stdout
    except Exception as e:
        logger.debug(f"Could not read clipboard: {e}")
        old_clipboard = ""

    logger.debug(f"Copying transcription to clipboard ({len(text)} chars)")
    subprocess.run(
        ["wl-copy"],
        input=text,
        text=True,
        check=True
    )

    time.sleep(0.05)

    logger.debug("Pasting text")
    subprocess.run(["wtype", "-M", "ctrl", "v", "-m", "ctrl"], check=True)

    time.sleep(0.05)

    # Restore original clipboard
    if old_clipboard:
        logger.debug("Restoring original clipboard")
        subprocess.run(
            ["wl-copy"],
            input=old_clipboard,
            text=True,
            check=False
        )


def stop_recording(max_duration=60, api_key=None, model=None):
    """Stop recording and transcribe audio."""
    logger.debug("Processing recording")

    if not PID_FILE.exists():
        logger.warning("No active recording found")
        notify("No active recording to process", error=True)
        return

    STOP_PID_FILE.write_text(str(os.getpid()))

    pid = int(PID_FILE.read_text().strip())
    logger.debug(f"Stopping recording (PID: {pid})")

    try:
        os.kill(pid, signal.SIGINT)
    except ProcessLookupError:
        logger.debug("Recording process already stopped")

    time.sleep(0.6)
    PID_FILE.unlink()

    if not AUDIO_FILE.exists():
        logger.error("Recording file not found")
        notify("Could not find recording file", error=True)
        STOP_PID_FILE.unlink(missing_ok=True)
        return

    notify("Analyzing audio...")
    try:
        speech_duration = remove_silence_vad(AUDIO_FILE)
    except Exception as e:
        logger.error(f"Failed to process audio: {e}", exc_info=True)
        notify("Failed to process audio", error=True)
        AUDIO_FILE.unlink(missing_ok=True)
        STOP_PID_FILE.unlink(missing_ok=True)
        return

    if speech_duration == 0:
        logger.info("No speech detected in recording")
        notify("No speech detected in recording")
        AUDIO_FILE.unlink()
        STOP_PID_FILE.unlink(missing_ok=True)
        return

    if speech_duration > max_duration:
        logger.warning(f"Recording too long: {speech_duration:.1f}s (max: {max_duration}s)")
        notify(f"Recording exceeded time limit ({int(speech_duration)}s of {max_duration}s max)")
        AUDIO_FILE.unlink()
        STOP_PID_FILE.unlink(missing_ok=True)
        return

    logger.info(f"Transcribing {speech_duration:.1f}s of speech")
    notify("Converting speech to text...")

    try:
        text = transcribe_audio(api_key, model)
        if text:
            paste_text(text)
            logger.info("Transcription completed successfully")
            notify("Text pasted successfully")
        else:
            logger.warning("Transcription service returned empty result")
            notify("No text was generated from the recording", error=True)
    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        notify("Failed to transcribe audio. Please try again.", error=True)
    finally:
        AUDIO_FILE.unlink(missing_ok=True)
        STOP_PID_FILE.unlink(missing_ok=True)
        logger.debug("Cleanup complete")


def main():
    parser = argparse.ArgumentParser(
        description="Convert your voice to text using AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nixspr start                              Begin recording
  nixspr process                            Stop and convert to text
  nixspr process --max-audio-duration 120   Allow up to 2 minutes
  nixspr cancel                             Cancel current operation

Configuration:
  Set your API key: export NIXSPR_GEMINI_API_KEY="your-key-here"
  Optional model:   export NIXSPR_GEMINI_MODEL="gemini-2.5-pro"
        """
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"nixspr {VERSION}"
    )

    parser.add_argument(
        "command",
        choices=["start", "process", "cancel"],
        help="start: begin recording | process: convert to text | cancel: stop"
    )

    parser.add_argument(
        "--max-audio-duration",
        type=int,
        default=60,
        metavar="SECONDS",
        help="maximum recording length in seconds (default: 60)"
    )

    parser.add_argument(
        "--gemini-api-key",
        type=str,
        metavar="KEY",
        help="your AI service key (alternative to environment variable)"
    )

    parser.add_argument(
        "--gemini-model",
        type=str,
        metavar="MODEL",
        help="AI model to use (default: gemini-2.5-flash)"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="show detailed technical information for troubleshooting"
    )

    args = parser.parse_args()

    # Setup logging
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        )
        logger.info("Debug logging enabled")
    else:
        logging.basicConfig(
            level=logging.WARNING,
            format="%(message)s"
        )

    logger.debug(f"Command: {args.command}")

    try:
        if args.command == "start":
            start_recording()
        elif args.command == "cancel":
            cancel_operation()
        else:  # process
            stop_recording(
                max_duration=args.max_audio_duration,
                api_key=args.gemini_api_key,
                model=args.gemini_model
            )
    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=args.debug)
        notify("An unexpected error occurred. Try again or use --debug for details.", error=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
