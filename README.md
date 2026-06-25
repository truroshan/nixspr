# Nixspr

Convert your voice to text instantly. Press a key to start recording, press again to stop—your words appear as typed text in any application.

## Features

- **Simple**: One keyboard shortcut to start/stop recording
- **Smart**: Automatically removes silence and pauses from your recording
- **Fast**: Text appears in seconds via your active window
- **Clean**: Removes "um", "uh" and repetitions automatically
- **Multilingual**: Supports Hindi with Roman script output (Hinglish)
- **Lists**: Detects and formats bullet points automatically
- **Safe**: Your clipboard is preserved—won't lose what you copied
- **Efficient**: Only processes speech, ignoring silence to save costs

## Installation

### Using Nix Flakes

```bash
# Run directly without installing
nix run github:truroshan/nixspr -- start
nix run github:truroshan/nixspr -- process

# Install to your profile
nix profile install github:truroshan/nixspr

# Or add to your NixOS configuration
{
  inputs.nixspr.url = "github:truroshan/nixspr";

  # Then in your configuration:
  environment.systemPackages = [
    inputs.nixspr.packages.${system}.default
  ];
}
```

### Local Development

```bash
# Setup environment (if using direnv)
cp .envrc.example .envrc
# Edit .envrc with your API key
direnv allow

# Or manually set environment variables
export NIXSPR_GEMINI_API_KEY="your-api-key-here"

# Enter development shell
nix develop

# Run the script
python3 nixspr.py start
python3 nixspr.py process

# Or build and run
nix build
./result/bin/nixspr start
```

## Setup

1. Obtain a Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)

2. Add your API key:

**Option A: For keyboard shortcut use (recommended)**
Add to your window manager config (see Keyboard Shortcuts section below)

**Option B: For command-line use**
Add to your shell profile (`~/.bashrc` or `~/.zshrc`):
```bash
export NIXSPR_GEMINI_API_KEY="your-api-key-here"
```

**Option C: Just testing**
Pass it directly when needed:
```bash
nixspr process --gemini-api-key "your-api-key-here"
```

## Usage

### Quick Start

```bash
# 1. Start recording
nixspr start

# 2. Speak your text

# 3. Stop and convert to text
nixspr process

# Your text will appear where your cursor is!
```

### Advanced Options

```bash
# Allow longer recordings (up to 2 minutes)
nixspr process --max-audio-duration 120

# Cancel anytime
nixspr cancel

# Troubleshooting mode
nixspr process --debug

# One-time API key (without setting environment variable)
nixspr process --gemini-api-key "your-key"

# Use different AI model
nixspr process --gemini-model "gemini-2.5-pro"
```

### Recording Limits

- **Maximum**: 60 seconds of actual speaking (pauses don't count)
- **No minimum**: Automatically detects if you actually spoke
- If you exceed the limit, you'll get a notification
- Silence and pauses are removed automatically—only your speech counts

### Keyboard Shortcuts

Set up a convenient keyboard shortcut for hands-free operation:
- **Alt+Space**: Start/stop recording
- **Alt+Shift+Space**: Cancel

**Example for niri window manager** (`~/.config/niri/config.kdl`):
```kdl
// Add your API key here
environment {
    NIXSPR_GEMINI_API_KEY "your-api-key-here"
}

binds {
    // Press once to start, again to convert to text
    Alt+Space { spawn "sh" "-c" "[ -f /tmp/nixspr.pid ] && nixspr process || nixspr start"; }

    // Cancel anytime
    Alt+Shift+Space { spawn "nixspr" "cancel"; }
}
```

## How It Works

1. **Press shortcut** → Recording starts
2. **Speak naturally** → Audio is captured
3. **Press shortcut again** → Processing begins:
   - Silence and pauses are removed
   - Your speech is converted to text by AI
   - Filler words ("um", "uh") are cleaned up
   - Text is formatted with punctuation
   - Result appears in your active window

## What It Can Do

**Clean Speech:**
- Removes "um", "uh", "like" automatically
- Eliminates repeated words
- Adds proper punctuation

**Smart Formatting:**
- Detects and creates bullet point lists
- Proper capitalization
- Handles mixed English and Hindi

**Hindi Support:**
- Converts Hindi speech to Roman script
- Example: Speaking "मुझे किताब चाहिए" becomes "mujhe kitaab chahiye"
- Works with mixed Hindi-English (Hinglish)

## What You Need

- **Linux** with Wayland display server (most modern Linux desktops)
- **Audio input** (microphone or headset)
- **Internet connection** (for AI processing)
- **API key** from Google AI Studio (free to get)

All software dependencies are automatically managed by Nix—nothing to install manually!

## Troubleshooting

### "API key not configured"
Set up your API key using one of these methods:
- Add to your shell: `export NIXSPR_GEMINI_API_KEY="your-key"`
- Add to window manager config (see Keyboard Shortcuts section)
- Pass directly: `nixspr process --gemini-api-key "your-key"`

### No audio is being recorded
Check your microphone:
```bash
pactl list sources short
pactl set-default-source <your-microphone-name>
```

### "No speech detected"
- Make sure your microphone is working
- Speak louder or closer to the microphone
- Check if other apps can hear your mic

### "Recording exceeded time limit"
- Default limit: 60 seconds of actual speech (pauses don't count)
- For longer recordings: `nixspr process --max-audio-duration 120`

### Text doesn't appear in the window
- Make sure the target window is active (clicked/focused)
- Try closing and restarting the application
- Test clipboard: `echo "test" | wl-copy` then paste manually

### Something's stuck
Run `nixspr cancel` to stop everything and try again

### Still having issues?
Run with `--debug` to see detailed information:
```bash
nixspr process --debug
```

## License

MIT
