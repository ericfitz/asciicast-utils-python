# asciicast-utils-python

These are Python utilities for recording, monitoring and playback of terminal sessions as asciicast files. This project provides a comprehensive terminal session recorder and interactive playback system that captures stdin, stdout, and stderr streams in real-time.

I built this so that I could use it as part of a project to monitor and record SSH terminal sessions to production hosts and keep a record of operator access.

Implemented with Claude Code, prompt file is in the repo.

## Features

### Recording (`record_session.py`)

- **Real-time terminal recording** with immediate file output
- **Separate stderr capture** and recording (format extension)
- **Automatic activity markers** inserted after gaps in user activity for better navigation during playback
- **Real-time monitoring server** with web interface and WebSocket streaming
- **Terminal state monitoring** including window resize detection
- **Cross-platform support** for macOS and Linux
- **Zero external dependencies** for recording - uses only Python standard library

### Playback (`playback_session.py`)

- **Interactive playback controls** with Space (pause/unpause) and Tab (skip to markers)
- **Cross-platform terminal window creation** for dedicated playback sessions
- **Real-time status updates** in terminal window title
- **Speed control** and maximum delay capping to skip long pauses
- **Activity marker navigation** for jumping to interesting events in the session
- **Clean playback experience** with no control artifacts in session output

### Monitoring (`monitor_session.py`) - _Optional_

- **Real-time session monitoring** via web browser interface gives an "over-the-shoulder" capability to monitor a session in progress.
- **WebSocket streaming** for live terminal output
- **Multiple client support** with session synchronization
- **Clean recording** with no monitoring artifacts in cast files

## Installation and Usage

### Recording Sessions

```bash
# Basic recording with uv
uv run record_session.py

# Traditional Python execution
python3 record_session.py --shell /bin/bash --output my_session.cast

# Recording with real-time monitoring
uv run record_session.py --monitor --output demo.cast

# Recording with custom shell and monitoring server
python3 record_session.py --shell /usr/bin/zsh --monitor --monitor-port 9999
```

### Playing Back Sessions

```bash
# Basic playback in new terminal window
python3 playback_session.py my_session.cast

# Playback with speed control and delay capping
python3 playback_session.py --speed 2.0 --max-delay 3.0 demo.cast

# Playback in current terminal (for debugging)
python3 playback_session.py --play-in-terminal session.cast
```

### Interactive Playback Controls

During playback in the dedicated terminal window:

- **Space**: Pause/unpause playback (status shown in window title)
- **Tab**: Skip to next input command or activity marker
- **Ctrl+C**: Stop playback

### Monitoring Sessions (Optional)

```bash
# Enable monitoring during recording
uv run record_session.py --monitor

# Open web browser to http://localhost:8888 to view live session
# Multiple browsers can connect simultaneously
```

### Command Line Options

#### record_session.py

- `--shell SHELL`: Shell to execute (default: `$SHELL` environment variable)
- `--output OUTPUT`: Output file path (default: auto-generated `recording_YYYYMMDD_HHMMSS.cast`)
- `--monitor`: Enable real-time monitoring server
- `--monitor-interface HOST`: Monitor server host (default: localhost)
- `--monitor-port PORT`: Monitor server port (default: 8888)
- `--monitor-buffer-size SIZE`: Buffer size for new clients (default: 1000)

#### playback_session.py

- `--speed FACTOR`: Playback speed multiplier (default: 1.0)
- `--max-delay SECONDS`: Maximum delay between events (default: 5.0)
- `--play-in-terminal`: Play in current terminal instead of new window

### Basic Workflow

1. **Record**: Run `record_session.py` with desired options
2. **Use normally**: The shell starts and all I/O is captured in real-time
3. **Monitor optionally**: Connect browser to monitoring server during recording
4. **Exit**: Type `exit` or press Ctrl+D to stop recording
5. **Playback**: Use `playback_session.py` for interactive session review

## Implementation Details

### Architecture Overview

The recorder uses a multi-process architecture:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   User Terminal │◄──►│  Python Recorder │◄──►│  Child Shell    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │  .cast File      │
                       │  (Real-time)     │
                       └──────────────────┘
```

### Core Technologies

- **PTY (Pseudo-Terminal)**: Creates a virtual terminal using `pty.openpty()` to capture all terminal I/O
- **Process Forking**: Uses `os.fork()` to create a child process running the target shell
- **I/O Multiplexing**: Uses `select.select()` to monitor multiple file descriptors simultaneously
- **Separate Pipes**: Creates dedicated pipes for stderr capture using `os.pipe()`

### Real-time Processing

The recorder processes and writes events immediately:

1. **Input Events**: Keystrokes are captured from user terminal, forwarded to child shell, and recorded
2. **Output Events**: Shell output is captured from PTY, echoed to user terminal, and recorded
3. **Error Events**: stderr is captured via separate pipe, echoed to user terminal, and recorded
4. **State Events**: Terminal attribute and window size changes are detected and recorded

## Enhanced Asciicast Format

### Standard asciicast v2 Events

- `"i"` - Input events (user keystrokes/stdin)
- `"o"` - Output events (stdout from shell)
- `"r"` - Resize events (terminal window size changes)
- `"m"` - Marker events (used for terminal attribute changes)

### Format Extensions

This implementation extends the standard asciicast v2 format with:

#### stderr Events (`"e"`)

```json
[1.234, "e", "Error: command not found\n"]
```

**Rationale**: Standard asciicast format doesn't distinguish between stdout and stderr. Our extension uses `"e"` events to capture stderr separately, enabling:

- Proper error stream analysis
- Better debugging of recorded sessions
- Accurate reproduction of original terminal behavior

#### Enhanced Resize Events (`"r"`)

```json
[2.567, "r", "24,80"]
```

**Format**: `"height,width"` - More precise than standard format

#### Terminal State Markers (`"m"`)

```json
[3.890, "m", "terminal_attrs_changed"]
[45.123, "m", "activity_resumed_after_5.2s"]
```

**Purpose**: Records terminal attribute changes and activity resumption markers:

- `terminal_attrs_changed`: Terminal settings modified (raw mode, echo, etc.)
- `activity_resumed_after_X.Xs`: Automatic markers inserted after 5+ second activity gaps

### File Structure Example

```json
{"version": 2, "width": 80, "height": 24, "timestamp": 1704067200, "command": "/bin/bash", "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"}}
[0.123, "o", "$ "]
[1.456, "i", "l"]
[1.457, "i", "s"]
[1.458, "i", "\r"]
[1.459, "o", "ls\r\n"]
[1.567, "o", "file1.txt  file2.txt\r\n"]
[2.234, "e", "ls: cannot access 'nonexistent': No such file or directory\n"]
[3.123, "r", "30,100"]
[4.567, "i", "exit\r"]
[4.568, "o", "exit\r\n"]
```

## Terminal State Monitoring

### Window Resize Detection

The recorder monitors terminal window size changes using:

- `fcntl.ioctl()` with `TIOCGWINSZ` to get current window dimensions
- Periodic polling during the I/O loop
- Automatic recording of resize events in asciicast format

### Terminal Attribute Monitoring

Tracks changes to terminal attributes including:

- Raw mode vs. cooked mode changes
- Echo settings modifications
- Control character mappings
- Line discipline changes

This enables accurate playback of programs that modify terminal behavior (like `vim`, `less`, etc.).

## Special Features and Workarounds

### Clean Recording with Monitoring

The monitoring server, if used, is designed to run completely invisibly during recording:

- **Silent mode**: All server logging is suppressed to prevent contamination of cast files
- **HTTP log suppression**: Access logs from web browser connections don't appear in recordings
- **Separate error handling**: Monitor server errors are handled separately from session errors

### Activity Gap Detection

- **Automatic markers**: Inserted after 5+ seconds of inactivity to create natural navigation points
- **Smart timing**: Markers are placed just before activity resumes for seamless playback
- **Enhanced navigation**: Tab key jumps to both input events and activity resumption points

### Cross-Platform Playback

- **Terminal window creation**: Automatically detects and uses available terminal emulators
- **macOS support**: Uses AppleScript to launch Terminal.app with proper session handling
- **Linux support**: Supports gnome-terminal, konsole, xterm, and x-terminal-emulator
- **Fallback behavior**: Gracefully falls back to current terminal if new window creation fails

### Responsive Playback Controls

- **Raw mode input**: Terminal set to raw mode to capture all keyboard input without echo
- **Non-blocking I/O**: Uses select() for responsive control handling during playback
- **Title bar feedback**: Status updates shown in terminal window title to keep session output clean
- **Input consumption**: Control keys are consumed and don't bleed through to session output

## Limitations and Known Issues

### Current Limitations

1. **Binary Data**: Uses UTF-8 decoding with error replacement - binary data may be corrupted
2. **Timing Precision**: Rapid I/O bursts may be batched together by the OS, losing sub-millisecond timing
3. **Format Compatibility**: Extended `"e"` events are non-standard and may not be supported by all asciicast players
4. **Signal Handling**: Some direct process signals may not be captured in the I/O stream
5. **Terminal Queries**: Complex terminal query/response sequences may not be fully captured

### Platform Support

- **Supported**: macOS, Linux (any Unix-like system with PTY support)
- **Not Supported**: Windows (lacks PTY support in standard library)
- **Requirements**: Python 3.8+ (uses standard library only)

### Performance Considerations

- **Memory Usage**: Minimal - events are written immediately to disk
- **CPU Usage**: Low - mostly I/O bound with efficient select() polling
- **Disk Usage**: Depends on session length and activity level
- **Real-time Overhead**: Negligible impact on recorded session performance

### Compatibility Notes

- Standard asciicast players should ignore unknown `"e"` events gracefully
- Resize and marker events use standard asciicast v2 event types
- Files are fully compatible with asciinema player for standard events
- Extended events require custom players or post-processing for full feature support

## Use Cases

### Development and Debugging

- Record terminal sessions for bug reports
- Capture stderr output separately for debugging
- Monitor terminal state changes during development

### Documentation and Training

- Create terminal-based tutorials
- Record command-line workflows
- Demonstrate shell scripting techniques

### System Administration

- Log shell sessions for security or compliance
- Record troubleshooting procedures
- Capture system diagnostic output

### Testing and CI/CD

- Record test execution sessions
- Capture build output and errors
- Create reproducible environment recordings

## File Format Details

### Header Structure

```json
{
  "version": 2,
  "width": 80,
  "height": 24,
  "timestamp": 1704067200,
  "command": "/bin/bash",
  "env": {
    "SHELL": "/bin/bash",
    "TERM": "xterm-256color"
  }
}
```

### Event Stream Format

Each line after the header is a JSON array: `[timestamp, event_type, data]`

- **timestamp**: Float with 3 decimal places precision
- **event_type**: String (`"i"`, `"o"`, `"e"`, `"r"`, `"m"`)
- **data**: String containing the actual content

### File Extension and MIME Type

- **Extension**: `.cast`
- **MIME Type**: `application/x-asciicast`
- **Encoding**: UTF-8 with newline-delimited JSON structure

## Troubleshooting

### Recording Issues

**"No module named 'websockets'" when using monitor**

- Monitor feature requires the `websockets` library
- Use `uv run record_session.py --monitor` to auto-install dependencies
- Or install manually: `pip install websockets>=10.0`

**Shell artifacts in recordings**

- Shell configuration (zsh, oh-my-zsh) may add messages like "Saving session..."
- Test with basic shell: `--shell /bin/sh` to isolate the source
- These are from shell hooks, not the recorder itself

### Playback Issues

**Controls (Space/Tab) not working**

- Ensure you're using the dedicated terminal window that opens
- If window doesn't open, check for supported terminal emulators:
  - macOS: Terminal.app (built-in)
  - Linux: gnome-terminal, konsole, xterm, x-terminal-emulator
- Use `--play-in-terminal` flag as fallback

**Long pauses in playback**

- Use `--max-delay 3.0` to cap long pauses at 3 seconds
- Activity markers help Tab navigation skip idle periods
- Adjust `--speed` to change overall playback speed

### Monitoring Issues

**HTTP access logs in recordings**

- Should be automatically suppressed in silent mode
- Test with: `grep -i "127.0.0.1\|GET\|POST" your_file.cast`
- If found, check monitor server silent mode implementation

**Monitor page won't load**

- Check firewall settings for specified port (default: 8888)
- Try different port: `--monitor-port 9999`
- Use `--monitor-interface 0.0.0.0` for network access (security risk)

### Platform-Specific Issues

**macOS Terminal window not opening**

- Check if Terminal.app has permissions
- Try manually: `osascript -e 'tell application "Terminal" to activate'`

**Linux terminal emulator not found**

- Install a supported terminal: `sudo apt install gnome-terminal`
- Or use fallback: `--play-in-terminal` flag

**PTY errors on older systems**

- Requires Python 3.8+ with full PTY support
- Check: `python3 -c "import pty; print('PTY OK')"`
