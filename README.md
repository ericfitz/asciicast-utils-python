# asciicast-utils-python

Python utilities for recording and playback of asciicast files. This project provides a comprehensive terminal session recorder that captures stdin, stdout, and stderr streams in real-time and saves them in asciicast format.

## Features

- **Real-time terminal recording** with immediate file output
- **Separate stderr capture** and recording (format extension)
- **Terminal state monitoring** including window resize detection
- **Cross-platform support** for macOS and Linux
- **Zero external dependencies** - uses only Python standard library
- **uv script support** with inline dependency management
- **Enhanced asciicast v2 format** with additional event types

## Installation and Usage

### Quick Start with uv

The script uses uv's inline script dependencies feature, so no virtual environment setup is required:

```bash
# Record a session with default shell and auto-generated filename
uv run record_session.py

# Specify shell and output file
uv run record_session.py --shell /bin/bash --output my_session.cast

# Use a different shell
uv run record_session.py --shell /usr/bin/zsh
```

### Traditional Python Execution

```bash
# Make script executable (first time only)
chmod +x record_session.py

# Run with Python directly
python3 record_session.py --shell /bin/bash --output session.cast
./record_session.py --output debug_session.cast
```

### Command Line Options

- `--shell SHELL`: Shell command to execute (default: `$SHELL` environment variable)
- `--output OUTPUT`: Output asciicast file path (default: auto-generated `recording_YYYYMMDD_HHMMSS.cast`)

### Basic Workflow

1. Run the script with desired options
2. The specified shell starts in a new session
3. All terminal I/O is captured in real-time
4. Use the shell normally - everything is recorded
5. Exit the shell (type `exit` or press Ctrl+D) to stop recording
6. The `.cast` file is saved with complete session data

## Implementation Details

### Architecture Overview

The recorder uses a sophisticated multi-process architecture:

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
```

**Purpose**: Records when terminal attributes change (raw mode, echo settings, etc.)

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

- Standard asciicast players will ignore unknown `"e"` events gracefully
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
- Log shell sessions for compliance
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