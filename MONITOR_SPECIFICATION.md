# Terminal Monitor Implementation Specification

## Overview

This specification defines the implementation of a real-time terminal monitoring system using WebSockets and xterm.js. The system allows multiple users to monitor terminal sessions in progress through a web browser interface.

## Architecture

```
┌─────────────────┐    ┌───────────────────────────┐    ┌─────────────────┐
│ User Terminal   │◄──►│ Python Recorder +         │◄──►│ Child Shell     │
│                 │    │ HTTP/WebSocket Server     │    │                 │
└─────────────────┘    └───────────────────────────┘    └─────────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │ Web Browser Clients       │
                        │ + xterm.js Terminal       │
                        │ + Monitor Utility         │
                        └───────────────────────────┘
```

## Component 1: Enhanced Recorder with Monitor Support

### Command Line Interface

The `record_session.py` script will be enhanced with optional monitoring parameters:

```bash
# Basic recording (no monitoring)
uv run record_session.py

# Recording with monitoring on default port and interface
uv run record_session.py --monitor

# Recording with custom port
uv run record_session.py --monitor --monitor-port 9999

# Recording with custom interface and port
uv run record_session.py --monitor --monitor-host 0.0.0.0 --monitor-port 8888

# Full example
uv run record_session.py --shell /bin/bash --output session.cast --monitor --monitor-host 192.168.1.100 --monitor-port 8080
```

### Command Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--monitor` | `False` | Enable terminal monitoring server |
| `--monitor-port` | `8888` | Port for HTTP server (WebSocket will use port+1) |
| `--monitor-host` | `localhost` | Interface to bind to (`localhost`, `0.0.0.0`, specific IP) |
| `--monitor-buffer-size` | `1000` | Number of recent output chunks to buffer for new clients |

### Implementation Requirements

#### 1. Server Architecture

```python
class WebSocketMonitorServer:
    """
    Dual-server setup:
    - HTTP server on specified port (serves web interface)
    - WebSocket server on port+1 (handles real-time communication)
    """
    
    def __init__(self, host: str = "localhost", port: int = 8888, buffer_size: int = 1000):
        self.host = host
        self.http_port = port
        self.websocket_port = port + 1
        self.buffer_size = buffer_size
        self.clients = set()
        self.terminal_state = TerminalState(buffer_size)
        
    def start_server(self):
        """Start both HTTP and WebSocket servers concurrently."""
        pass
        
    async def broadcast_event(self, event_type: str, data: str):
        """Broadcast terminal events to all connected clients."""
        pass
```

#### 2. Terminal State Management

```python
class TerminalState:
    """
    Maintains terminal state and output buffer for client synchronization.
    """
    
    def __init__(self, buffer_size: int = 1000):
        self.width = 80
        self.height = 24
        self.recent_output = collections.deque(maxlen=buffer_size)
        self.session_metadata = {}
        
    def process_output(self, event_type: str, data: str):
        """Process and store terminal output."""
        self.recent_output.append({
            'timestamp': time.time(),
            'event_type': event_type,
            'data': data
        })
        
    def get_sync_data(self) -> dict:
        """Get state data for new client synchronization."""
        return {
            'type': 'terminal_sync',
            'session_metadata': self.session_metadata,
            'terminal_size': {'width': self.width, 'height': self.height},
            'recent_output': list(self.recent_output)[-100:],  # Last 100 events
            'buffer_info': {
                'total_events': len(self.recent_output),
                'sync_time': time.time()
            }
        }
```

#### 3. Integration Points

The monitor server integrates with the existing recorder at these points:

```python
class AsciinemaRecorder:
    def __init__(self, output_file: str, shell_command: str, 
                 monitor_enabled: bool = False, 
                 monitor_host: str = "localhost", 
                 monitor_port: int = 8888):
        # ... existing init code ...
        self.monitor_server = None
        if monitor_enabled:
            self.monitor_server = WebSocketMonitorServer(
                host=monitor_host, 
                port=monitor_port
            )
    
    def write_event(self, event_type: str, data: str) -> None:
        """Enhanced to broadcast to monitor clients."""
        # ... existing asciicast writing code ...
        
        # Broadcast to monitor clients
        if self.monitor_server:
            asyncio.create_task(
                self.monitor_server.broadcast_event(event_type, data)
            )
```

### Server Startup Messages

When monitoring is enabled, the recorder will display:

```
Recording session to: /path/to/recording.cast
Shell: /bin/bash
Monitor server starting...
  HTTP server: http://192.168.1.100:8888
  WebSocket server: ws://192.168.1.100:8889
Monitor server ready. Use monitor utility or open URL in browser.

Press Ctrl+C or exit shell to stop recording
```

## Component 2: Standalone Monitor Utility

### Purpose

A command-line utility that opens a browser window and connects to a monitoring session.

### Usage

```bash
# Basic usage
uv run monitor_session.py http://localhost:8888

# Connect to remote session
uv run monitor_session.py http://192.168.1.100:8888

# With custom browser
uv run monitor_session.py --browser firefox http://server.example.com:9999

# List available sessions (if discovery is implemented)
uv run monitor_session.py --list
```

### Command Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `url` | Required | URL of the monitor server (http://host:port) |
| `--browser` | System default | Browser to use (`chrome`, `firefox`, `safari`, `default`) |
| `--no-open` | `False` | Don't auto-open browser, just show URL |
| `--list` | `False` | List available sessions on local network (future feature) |

### Implementation

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = ["websockets>=10.0"]
# ///

import argparse
import webbrowser
import sys
import urllib.parse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description="Connect to terminal monitoring session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  monitor_session.py http://localhost:8888
  monitor_session.py --browser firefox http://192.168.1.100:8888
  monitor_session.py --no-open http://server.example.com:9999
        """
    )
    
    parser.add_argument("url", help="Monitor server URL (http://host:port)")
    parser.add_argument("--browser", help="Browser to use (chrome, firefox, safari, default)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    
    args = parser.parse_args()
    
    # Validate URL
    parsed_url = urllib.parse.urlparse(args.url)
    if not parsed_url.scheme or not parsed_url.netloc:
        print(f"Error: Invalid URL format: {args.url}")
        print("Expected format: http://hostname:port")
        sys.exit(1)
    
    if args.no_open:
        print(f"Monitor URL: {args.url}")
        print("Open this URL in your browser to view the terminal session.")
    else:
        print(f"Opening monitor session: {args.url}")
        
        if args.browser:
            # Try to use specific browser
            browser_map = {
                'chrome': 'google-chrome',
                'firefox': 'firefox', 
                'safari': 'safari'
            }
            browser_cmd = browser_map.get(args.browser.lower(), args.browser)
            try:
                webbrowser.get(browser_cmd).open(args.url)
            except webbrowser.Error:
                print(f"Warning: Could not open {args.browser}, using default browser")
                webbrowser.open(args.url)
        else:
            webbrowser.open(args.url)
        
        print("Browser opened. If the session is active, you should see terminal output.")
        print("Press Ctrl+C to exit this utility (won't affect the session).")
        
        try:
            input()  # Keep utility running
        except KeyboardInterrupt:
            print("\nMonitor utility exiting.")

if __name__ == "__main__":
    main()
```

## WebSocket Protocol Specification

### Message Types

#### 1. Client → Server Messages

```json
{
  "type": "client_hello",
  "client_info": {
    "user_agent": "Mozilla/5.0...",
    "terminal_size": {"width": 120, "height": 40}
  }
}
```

```json
{
  "type": "terminal_resize", 
  "size": {"width": 100, "height": 30}
}
```

#### 2. Server → Client Messages

**Initial Synchronization:**
```json
{
  "type": "terminal_sync",
  "session_metadata": {
    "session_id": "rec_20240115_143022",
    "start_time": 1704067200,
    "shell_command": "/bin/bash",
    "recording_file": "session.cast"
  },
  "terminal_size": {"width": 80, "height": 24},
  "recent_output": [
    {
      "timestamp": 1704067201.123,
      "event_type": "o",
      "data": "$ ls -la\r\n"
    },
    {
      "timestamp": 1704067201.456, 
      "event_type": "o",
      "data": "total 48\r\n"
    }
  ],
  "buffer_info": {
    "total_events": 245,
    "showing_recent": 100,
    "sync_time": 1704067301.789
  }
}
```

**Real-time Data:**
```json
{
  "type": "terminal_data",
  "timestamp": 1704067302.123,
  "event_type": "o",
  "data": "file1.txt  file2.txt\r\n"
}
```

**Session Events:**
```json
{
  "type": "session_event",
  "event": "client_connected",
  "data": {"client_count": 3}
}
```

```json
{
  "type": "session_event", 
  "event": "session_ended",
  "data": {"reason": "shell_exit", "timestamp": 1704067400.000}
}
```

## Web Interface Specification

### HTML Template Structure

The HTTP server serves a single-page application with:

1. **Status Bar**: Connection status, session info, client count
2. **Terminal Area**: xterm.js terminal emulator
3. **Control Panel**: Fullscreen toggle, font size controls
4. **Connection Info**: Mid-stream join notification

### JavaScript Client Behavior

#### Connection Handling
```javascript
const wsUrl = `ws://${window.location.hostname}:${parseInt(window.location.port) + 1}`;
const ws = new WebSocket(wsUrl);

ws.onopen = () => {
    updateStatus('Connected', 'success');
    ws.send(JSON.stringify({
        type: 'client_hello',
        client_info: {
            user_agent: navigator.userAgent,
            terminal_size: {width: term.cols, height: term.rows}
        }
    }));
};
```

#### Mid-Stream Synchronization
```javascript
function handleTerminalSync(data) {
    // Clear terminal and show sync message
    term.clear();
    showSyncNotification(data.buffer_info);
    
    // Resize terminal to match session
    term.resize(data.terminal_size.width, data.terminal_size.height);
    
    // Replay recent output with progress indication
    replayOutput(data.recent_output, () => {
        showLiveIndicator();
    });
}

function replayOutput(events, callback) {
    let index = 0;
    const replaySpeed = 5; // events per batch
    
    function replayBatch() {
        const batch = events.slice(index, index + replaySpeed);
        batch.forEach(event => {
            if (event.event_type === 'o' || event.event_type === 'e') {
                term.write(event.data);
            }
        });
        
        index += replaySpeed;
        if (index < events.length) {
            requestAnimationFrame(replayBatch);
        } else {
            callback();
        }
    }
    
    replayBatch();
}
```

### User Interface Features

1. **Connection Status Indicator**
   - Green: Connected and receiving data
   - Yellow: Connected but no recent data  
   - Red: Disconnected

2. **Session Information Panel**
   - Session start time
   - Shell command being recorded
   - Number of connected monitors
   - Recording file name

3. **Mid-Stream Join Notification**
   ```
   ┌─────────────────────────────────────────────────────┐
   │ 📺 Joined session in progress                       │
   │ Started: 2024-01-15 14:30:22                        │
   │ Showing last 100 events (2.3 minutes of output)    │ 
   │ Live output begins below...                         │
   └─────────────────────────────────────────────────────┘
   ```

4. **Terminal Controls**
   - Font size adjustment (+/-)
   - Fullscreen toggle
   - Copy mode toggle
   - Clear screen (client-side only)

## Implementation Roadmap

### Phase 1: Core Functionality
- [ ] Implement WebSocketMonitorServer class
- [ ] Integrate with existing AsciinemaRecorder
- [ ] Create basic HTML/JavaScript client
- [ ] Implement terminal state synchronization
- [ ] Add command line arguments to recorder

### Phase 2: Standalone Monitor Utility  
- [ ] Implement monitor_session.py utility
- [ ] Add browser detection and launching
- [ ] Add URL validation and error handling
- [ ] Test cross-platform browser opening

### Phase 3: Enhanced Features
- [ ] Add session metadata display
- [ ] Implement connection status indicators
- [ ] Add terminal control features (font size, fullscreen)
- [ ] Optimize mid-stream synchronization

### Phase 4: Polish and Testing
- [ ] Add comprehensive error handling
- [ ] Implement graceful shutdown procedures  
- [ ] Add logging and debugging options
- [ ] Test with various terminal applications
- [ ] Performance testing with multiple clients

## Security Considerations

1. **Default Binding**: Default to `localhost` to prevent accidental exposure
2. **No Authentication**: Initial implementation has no auth (suitable for development)
3. **Resource Limits**: Limit number of concurrent clients (default: 10)
4. **Input Filtering**: Monitor clients are read-only (no input to recorded session)

## Dependencies

The implementation adds one external dependency:

```python
# /// script
# requires-python = ">=3.8"
# dependencies = ["websockets>=10.0"]
# ///
```

This maintains the project's minimal dependency philosophy while enabling robust WebSocket functionality.

## Future Enhancements

1. **Session Discovery**: Auto-discovery of sessions on local network
2. **Authentication**: Simple token-based authentication for remote access
3. **Recording Playback**: Monitor interface for playing back completed `.cast` files
4. **Multi-Session Support**: Single monitor server handling multiple concurrent recordings
5. **Mobile Support**: Responsive design for mobile terminal monitoring

## Testing Strategy

1. **Unit Tests**: Test WebSocket message handling and terminal state management
2. **Integration Tests**: Test recorder + monitor server integration  
3. **Browser Tests**: Test client JavaScript in multiple browsers
4. **Network Tests**: Test remote monitoring scenarios
5. **Load Tests**: Test multiple concurrent monitor clients
6. **Terminal App Tests**: Test monitoring of complex applications (vim, htop, etc.)