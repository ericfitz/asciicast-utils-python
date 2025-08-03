# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python utilities for recording and playback of asciicast files. The main functionality is a terminal session recorder that captures stdin/stdout/stderr and saves sessions in asciicast v2 format.

## Running the Scripts

The main script uses uv's inline script dependencies feature:

```bash
# Record a session with default shell and auto-generated filename
uv run record_session.py

# Specify shell and output file
uv run record_session.py --shell /bin/bash --output my_session.cast

# Traditional Python execution also works
python3 record_session.py --shell zsh
```

## Code Architecture

### record_session.py
The main terminal recording script built around the `AsciinemaRecorder` class:

- **PTY-based capture**: Uses `pty.openpty()` and `os.fork()` to create a pseudo-terminal that captures all I/O
- **Real-time processing**: Uses `select.select()` to monitor multiple file descriptors simultaneously
- **Asciicast v2 format**: Writes newline-delimited JSON with header + event stream
- **Cross-platform**: Works on macOS and Linux using standard library modules

Key implementation details:
- Timestamps rounded to 3 decimal places for asciicast output
- Terminal settings preserved and restored using `termios`
- Signal forwarding (Ctrl+C) to child processes
- Automatic terminal size detection and PTY configuration

### Asciicast Format
The script generates asciicast v2 files:
- Header: JSON object with version, dimensions, timestamp, shell command
- Events: JSON arrays `[timestamp, event_type, data]` where event_type is "i" (input) or "o" (output)

## Development Notes

The project uses no external dependencies beyond Python 3.8+ standard library. The uv script configuration is embedded in the file header using PEP 723 inline script metadata.