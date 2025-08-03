#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = ["websockets>=10.0"]
# ///

import argparse
import asyncio
import collections
import fcntl
import json
import os
import pty
import select
import shutil
import signal
import struct
import sys
import termios
import threading
import time
import tty
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional, TextIO, Set
import websockets


class TerminalState:
    """Maintains terminal state and output buffer for client synchronization."""
    
    def __init__(self, buffer_size: int = 1000):
        self.width = 80
        self.height = 24
        self.recent_output = collections.deque(maxlen=buffer_size)
        self.session_metadata = {}
        self.start_time = time.time()
        
    def set_session_metadata(self, shell_command: str, output_file: str):
        """Set session metadata for client display."""
        self.session_metadata = {
            'session_id': f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'start_time': self.start_time,
            'shell_command': shell_command,
            'recording_file': output_file
        }
        
    def set_terminal_size(self, width: int, height: int):
        """Update terminal dimensions."""
        self.width = width
        self.height = height
        
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
                'showing_recent': min(100, len(self.recent_output)),
                'sync_time': time.time()
            }
        }


class MonitorHTTPHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves the monitor web interface."""
    
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(self._get_terminal_html().encode())
        else:
            self.send_error(404, "File not found")
            
    def _get_terminal_html(self):
        """Generate the HTML interface for terminal monitoring."""
        websocket_port = self.server.websocket_port
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Terminal Monitor</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@4.19.0/css/xterm.css" />
    <script src="https://cdn.jsdelivr.net/npm/xterm@4.19.0/lib/xterm.js"></script>
    <style>
        body {{ 
            margin: 0; 
            padding: 20px; 
            background: #1e1e1e; 
            color: #fff; 
            font-family: 'Courier New', monospace;
        }}
        #terminal-container {{ 
            width: 100%; 
            height: 80vh; 
            border: 1px solid #333;
            border-radius: 4px;
        }}
        #status-bar {{
            margin-bottom: 10px;
            padding: 10px;
            background: #333;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        #connection-status {{
            font-weight: bold;
        }}
        #connection-status.connected {{ color: #0f0; }}
        #connection-status.connecting {{ color: #ff0; }}
        #connection-status.disconnected {{ color: #f00; }}
        #session-info {{ color: #ccc; }}
        #sync-notification {{
            background: #444;
            border: 1px solid #666;
            padding: 10px;
            margin-bottom: 10px;
            border-radius: 4px;
            display: none;
        }}
        .controls {{
            margin-bottom: 10px;
            color: #ccc;
        }}
        .controls button {{
            background: #555;
            color: #fff;
            border: 1px solid #777;
            padding: 5px 10px;
            margin-right: 5px;
            border-radius: 3px;
            cursor: pointer;
        }}
        .controls button:hover {{ background: #666; }}
    </style>
</head>
<body>
    <div id="status-bar">
        <div id="connection-status" class="connecting">Connecting...</div>
        <div id="session-info"></div>
    </div>
    
    <div id="sync-notification">
        <strong>📺 Joined session in progress</strong><br>
        <span id="sync-details"></span>
    </div>
    
    <div class="controls">
        <button onclick="toggleFullscreen()">Fullscreen</button>
        <button onclick="adjustFontSize(1)">Font +</button>
        <button onclick="adjustFontSize(-1)">Font -</button>
        <button onclick="clearTerminal()">Clear View</button>
    </div>
    
    <div id="terminal-container"></div>
    
    <script>
        const term = new Terminal({{
            cursorBlink: true,
            fontSize: 14,
            fontFamily: 'Courier New, monospace',
            theme: {{
                background: '#000000',
                foreground: '#ffffff',
                cursor: '#ffffff',
                selection: '#444444'
            }}
        }});
        
        const container = document.getElementById('terminal-container');
        const statusElement = document.getElementById('connection-status');
        const sessionInfo = document.getElementById('session-info');
        const syncNotification = document.getElementById('sync-notification');
        const syncDetails = document.getElementById('sync-details');
        
        term.open(container);
        
        // WebSocket connection
        const wsUrl = `ws://${{window.location.hostname}}:{websocket_port}`;
        const ws = new WebSocket(wsUrl);
        
        let isConnected = false;
        let currentFontSize = 14;
        
        ws.onopen = function() {{
            updateConnectionStatus('connected', 'Connected');
            isConnected = true;
        }};
        
        ws.onmessage = function(event) {{
            const data = JSON.parse(event.data);
            
            if (data.type === 'terminal_sync') {{
                handleTerminalSync(data);
            }} else if (data.type === 'terminal_data') {{
                term.write(data.data);
            }} else if (data.type === 'session_event') {{
                handleSessionEvent(data);
            }}
        }};
        
        ws.onclose = function() {{
            updateConnectionStatus('disconnected', 'Disconnected');
            isConnected = false;
        }};
        
        ws.onerror = function() {{
            updateConnectionStatus('disconnected', 'Connection Error');
            isConnected = false;
        }};
        
        function handleTerminalSync(data) {{
            // Update session information
            const meta = data.session_metadata;
            const startTime = new Date(meta.start_time * 1000).toLocaleString();
            sessionInfo.textContent = `Session: ${{meta.shell_command}} | Started: ${{startTime}}`;
            
            // Show sync notification
            const bufferInfo = data.buffer_info;
            syncDetails.innerHTML = `
                Started: ${{startTime}}<br>
                Showing last ${{bufferInfo.showing_recent}} events (${{bufferInfo.total_events}} total)<br>
                <em>Live output begins below...</em>
            `;
            syncNotification.style.display = 'block';
            
            // Resize terminal to match session
            term.resize(data.terminal_size.width, data.terminal_size.height);
            
            // Clear and replay recent output
            term.clear();
            replayOutput(data.recent_output, function() {{
                // Hide sync notification after a delay
                setTimeout(() => {{
                    syncNotification.style.display = 'none';
                }}, 3000);
            }});
        }}
        
        function replayOutput(events, callback) {{
            let index = 0;
            const replaySpeed = 5; // events per batch
            
            function replayBatch() {{
                const batch = events.slice(index, index + replaySpeed);
                batch.forEach(event => {{
                    if (event.event_type === 'o' || event.event_type === 'e') {{
                        term.write(event.data);
                    }}
                }});
                
                index += replaySpeed;
                if (index < events.length) {{
                    requestAnimationFrame(replayBatch);
                }} else if (callback) {{
                    callback();
                }}
            }}
            
            if (events.length > 0) {{
                replayBatch();
            }} else if (callback) {{
                callback();
            }}
        }}
        
        function handleSessionEvent(data) {{
            if (data.event === 'session_ended') {{
                updateConnectionStatus('disconnected', 'Session Ended');
                term.write('\\r\\n\\x1b[33m[SESSION ENDED]\\x1b[0m\\r\\n');
            }}
        }}
        
        function updateConnectionStatus(status, message) {{
            statusElement.className = status;
            statusElement.textContent = message;
        }}
        
        // Control functions
        function toggleFullscreen() {{
            if (!document.fullscreenElement) {{
                document.documentElement.requestFullscreen();
            }} else {{
                document.exitFullscreen();
            }}
        }}
        
        function adjustFontSize(delta) {{
            currentFontSize = Math.max(8, Math.min(24, currentFontSize + delta));
            term.options.fontSize = currentFontSize;
            term.refresh(0, term.rows - 1);
        }}
        
        function clearTerminal() {{
            term.clear();
        }}
        
        // Handle window resize
        window.addEventListener('resize', () => {{
            setTimeout(() => {{ term.fit(); }}, 100);
        }});
        
        // Auto-resize terminal
        setTimeout(() => {{ term.fit(); }}, 100);
    </script>
</body>
</html>
        """


class WebSocketMonitorServer:
    """WebSocket server for real-time terminal monitoring."""
    
    def __init__(self, host: str = "localhost", port: int = 8888, buffer_size: int = 1000):
        self.host = host
        self.http_port = port
        self.websocket_port = port + 1
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.terminal_state = TerminalState(buffer_size)
        self.http_server = None
        self.websocket_server = None
        self.running = False
        self.event_loop = None
        self.broadcast_queue = None
        
    def start_server(self):
        """Start both HTTP and WebSocket servers."""
        print(f"Monitor server starting...")
        print(f"  HTTP server: http://{self.host}:{self.http_port}")
        print(f"  WebSocket server: ws://{self.host}:{self.websocket_port}")
        
        # Start HTTP server in separate thread
        http_thread = threading.Thread(target=self._start_http_server, daemon=True)
        http_thread.start()
        
        # Start WebSocket server in asyncio event loop
        self.event_loop = asyncio.new_event_loop()
        
        self.running = True
        websocket_thread = threading.Thread(
            target=self._run_websocket_server,
            daemon=True
        )
        websocket_thread.start()
        
        print("Monitor server ready. Use monitor utility or open URL in browser.")
        
    def _run_websocket_server(self):
        """Run the WebSocket server in its own event loop."""
        asyncio.set_event_loop(self.event_loop)
        
        # Create the broadcast queue in the correct event loop
        self.broadcast_queue = asyncio.Queue()
        
        # Start the broadcast queue processor
        self.event_loop.create_task(self._process_broadcast_queue())
        
        # Start the WebSocket server
        server = websockets.serve(
            self.handle_websocket_client,
            self.host,
            self.websocket_port
        )
        
        self.event_loop.run_until_complete(server)
        self.event_loop.run_forever()
        
    async def _process_broadcast_queue(self):
        """Process broadcast events from the queue."""
        while self.running:
            try:
                # Wait for broadcast events
                event_type, data = await asyncio.wait_for(
                    self.broadcast_queue.get(), 
                    timeout=1.0
                )
                await self.broadcast_event(event_type, data)
            except asyncio.TimeoutError:
                continue
            except Exception:
                continue
                
    def schedule_broadcast(self, event_type: str, data: str):
        """Schedule a broadcast from the main thread."""
        if self.event_loop and self.running:
            try:
                # Thread-safe way to add to queue
                self.event_loop.call_soon_threadsafe(
                    self.broadcast_queue.put_nowait, 
                    (event_type, data)
                )
            except:
                pass  # Queue full or loop closed
        
    def _start_http_server(self):
        """Start HTTP server for serving web interface."""
        class CustomHTTPServer(HTTPServer):
            def __init__(self, server_address, RequestHandlerClass, websocket_port):
                super().__init__(server_address, RequestHandlerClass)
                self.websocket_port = websocket_port
        
        self.http_server = CustomHTTPServer(
            (self.host, self.http_port), 
            MonitorHTTPHandler, 
            self.websocket_port
        )
        self.http_server.serve_forever()
        
    async def handle_websocket_client(self, websocket, path):
        """Handle new WebSocket client connection."""
        self.clients.add(websocket)
        print(f"Monitor client connected from {websocket.remote_address}. Total clients: {len(self.clients)}")
        
        try:
            # Send current terminal state to new client
            sync_data = self.terminal_state.get_sync_data()
            await websocket.send(json.dumps(sync_data))
            
            # Keep connection alive and handle client messages
            async for message in websocket:
                # Handle client messages (e.g., resize notifications)
                try:
                    data = json.loads(message)
                    if data.get('type') == 'client_hello':
                        # Client connected successfully
                        pass
                except json.JSONDecodeError:
                    pass
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.discard(websocket)
            print(f"Monitor client disconnected. Total clients: {len(self.clients)}")
            
    async def broadcast_event(self, event_type: str, data: str):
        """Broadcast terminal events to all connected clients."""
        if not self.clients or not self.running:
            return
            
        # Update terminal state
        self.terminal_state.process_output(event_type, data)
        
        # Prepare message for clients
        message = {
            'type': 'terminal_data',
            'timestamp': time.time(),
            'event_type': event_type,
            'data': data
        }
        
        # Send to all clients
        if self.clients:
            message_json = json.dumps(message)
            disconnected = set()
            
            for client in self.clients.copy():
                try:
                    await client.send(message_json)
                except websockets.exceptions.ConnectionClosed:
                    disconnected.add(client)
                    
            # Clean up disconnected clients
            self.clients -= disconnected
            
    def stop_server(self):
        """Stop the monitor server."""
        self.running = False
        if self.http_server:
            self.http_server.shutdown()


class AsciinemaRecorder:
    def __init__(self, output_file: str, shell_command: str, 
                 monitor_enabled: bool = False, 
                 monitor_host: str = "localhost", 
                 monitor_port: int = 8888,
                 monitor_buffer_size: int = 1000):
        self.output_file = output_file
        self.shell_command = shell_command
        self.start_time = time.time()
        self.cast_file: Optional[TextIO] = None
        self.original_tty_settings = None
        self.last_terminal_attrs = None
        self.last_winsize = None
        
        # Monitor server setup
        self.monitor_server = None
        if monitor_enabled:
            self.monitor_server = WebSocketMonitorServer(
                host=monitor_host, 
                port=monitor_port,
                buffer_size=monitor_buffer_size
            )
        
    def get_terminal_size(self) -> tuple[int, int]:
        """Get current terminal dimensions."""
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    
    def write_header(self) -> None:
        """Write asciicast v2 header to output file."""
        width, height = self.get_terminal_size()
        header = {
            "version": 2,
            "width": width,
            "height": height,
            "timestamp": int(self.start_time),
            "command": self.shell_command,
            "env": {
                "SHELL": os.environ.get("SHELL", "/bin/sh"),
                "TERM": os.environ.get("TERM", "xterm-256color"),
            }
        }
        
        self.cast_file = open(self.output_file, 'w')
        self.cast_file.write(json.dumps(header) + '\n')
        self.cast_file.flush()
        
        # Initialize monitor server if enabled
        if self.monitor_server:
            self.monitor_server.terminal_state.set_terminal_size(width, height)
            self.monitor_server.terminal_state.set_session_metadata(
                self.shell_command, 
                self.output_file
            )
    
    def check_terminal_state_changes(self, master_fd: int) -> None:
        """Check for terminal state changes and record them."""
        try:
            # Check terminal attributes
            current_attrs = termios.tcgetattr(master_fd)
            if self.last_terminal_attrs is None:
                self.last_terminal_attrs = current_attrs
            elif current_attrs != self.last_terminal_attrs:
                self.write_event("m", f"terminal_attrs_changed")
                self.last_terminal_attrs = current_attrs
            
            # Check window size
            try:
                winsize_data = fcntl.ioctl(master_fd, termios.TIOCGWINSZ, b'\x00' * 8)
                current_winsize = struct.unpack('HHHH', winsize_data)
                if self.last_winsize is None:
                    self.last_winsize = current_winsize
                elif current_winsize != self.last_winsize:
                    height, width = current_winsize[:2]
                    self.write_event("r", f"{height},{width}")
                    self.last_winsize = current_winsize
            except (OSError, IOError):
                pass
                
        except (OSError, IOError, termios.error):
            pass
    
    def write_event(self, event_type: str, data: str) -> None:
        """Write an event to the asciicast file and broadcast to monitors."""
        if self.cast_file:
            timestamp = round(time.time() - self.start_time, 3)
            event = [timestamp, event_type, data]
            self.cast_file.write(json.dumps(event) + '\n')
            self.cast_file.flush()
            
            # Broadcast to monitor clients (only output events)
            if self.monitor_server and event_type in ['o', 'e']:
                # Schedule broadcast in the WebSocket event loop
                self.monitor_server.schedule_broadcast(event_type, data)
    
    def setup_terminal(self) -> None:
        """Setup terminal for raw input capture."""
        if os.isatty(sys.stdin.fileno()):
            self.original_tty_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())
    
    def restore_terminal(self) -> None:
        """Restore original terminal settings."""
        if self.original_tty_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.original_tty_settings)
    
    def record_session(self) -> None:
        """Main recording loop using pty."""
        self.write_header()
        self.setup_terminal()
        
        # Start monitor server if enabled
        if self.monitor_server:
            self.monitor_server.start_server()
        
        try:
            # Create pseudo-terminal
            master_fd, slave_fd = pty.openpty()
            
            # Create separate pipe for stderr
            stderr_read, stderr_write = os.pipe()
            
            # Copy terminal size to pty
            width, height = self.get_terminal_size()
            try:
                winsize = struct.pack('HHHH', height, width, 0, 0)
                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
            except (OSError, IOError):
                # Fallback - continue without setting window size
                pass
            
            # Fork process
            pid = os.fork()
            
            if pid == 0:
                # Child process - execute shell
                os.close(master_fd)
                os.close(stderr_read)
                os.setsid()
                os.dup2(slave_fd, 0)  # stdin
                os.dup2(slave_fd, 1)  # stdout
                os.dup2(stderr_write, 2)  # stderr to separate pipe
                os.close(slave_fd)
                os.close(stderr_write)
                
                # Execute the shell command
                os.execv(self.shell_command, [self.shell_command])
            else:
                # Parent process - handle I/O
                os.close(slave_fd)
                os.close(stderr_write)
                
                try:
                    self._handle_io(master_fd, stderr_read, pid)
                finally:
                    os.close(master_fd)
                    os.close(stderr_read)
                    # Wait for child process
                    try:
                        os.waitpid(pid, 0)
                    except OSError:
                        pass
                        
        except Exception as e:
            print(f"Error during recording: {e}", file=sys.stderr)
        finally:
            self.restore_terminal()
            if self.cast_file:
                self.cast_file.close()
    
    def _handle_io(self, master_fd: int, stderr_fd: int, child_pid: int) -> None:
        """Handle input/output between terminal and pty."""
        stdin_fd = sys.stdin.fileno()
        stdout_fd = sys.stdout.fileno()
        stderr_out_fd = sys.stderr.fileno()
        
        while True:
            try:
                # Use select to monitor file descriptors
                ready_fds, _, _ = select.select([stdin_fd, master_fd, stderr_fd], [], [], 0.1)
                
                # Check for terminal state changes periodically
                self.check_terminal_state_changes(master_fd)
                
                # Check if child process is still alive
                try:
                    pid, status = os.waitpid(child_pid, os.WNOHANG)
                    if pid != 0:  # Child has exited
                        break
                except OSError:
                    break
                
                for fd in ready_fds:
                    if fd == stdin_fd:
                        # Input from user terminal
                        try:
                            data = os.read(stdin_fd, 1024)
                            if data:
                                # Write to pty master (sends to child)
                                os.write(master_fd, data)
                                # Record input event
                                self.write_event("i", data.decode('utf-8', errors='replace'))
                        except OSError:
                            return
                    
                    elif fd == master_fd:
                        # Output from child process (stdout)
                        try:
                            data = os.read(master_fd, 1024)
                            if data:
                                # Echo to user terminal
                                os.write(stdout_fd, data)
                                # Record output event
                                self.write_event("o", data.decode('utf-8', errors='replace'))
                            else:
                                # EOF from child
                                return
                        except OSError:
                            return
                    
                    elif fd == stderr_fd:
                        # Error output from child process (stderr)
                        try:
                            data = os.read(stderr_fd, 1024)
                            if data:
                                # Echo to user terminal stderr
                                os.write(stderr_out_fd, data)
                                # Record stderr event (using "e" for stderr)
                                self.write_event("e", data.decode('utf-8', errors='replace'))
                            else:
                                # EOF from stderr pipe
                                pass
                        except OSError:
                            pass
                            
            except KeyboardInterrupt:
                # Forward interrupt to child
                try:
                    os.kill(child_pid, signal.SIGINT)
                except OSError:
                    pass
            except Exception:
                break


def generate_output_filename() -> str:
    """Generate a unique output filename in current directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"recording_{timestamp}.cast"


def main():
    parser = argparse.ArgumentParser(
        description="Record terminal session to asciicast format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python record_session.py
  python record_session.py --shell /bin/bash --output my_session.cast
  uv run record_session.py --shell zsh
  
Monitor examples:
  python record_session.py --monitor
  python record_session.py --monitor --monitor-port 9999
  python record_session.py --monitor --monitor-host 0.0.0.0 --monitor-port 8888
        """
    )
    
    parser.add_argument(
        "--shell",
        help="Shell command to execute (default: $SHELL environment variable)"
    )
    
    parser.add_argument(
        "--output",
        help="Output asciicast file path (default: auto-generated in current directory)"
    )
    
    # Monitor options
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Enable terminal monitoring server"
    )
    
    parser.add_argument(
        "--monitor-port",
        type=int,
        default=8888,
        help="Port for monitor HTTP server (WebSocket will use port+1, default: 8888)"
    )
    
    parser.add_argument(
        "--monitor-host",
        default="localhost",
        help="Interface to bind monitor server to (default: localhost)"
    )
    
    parser.add_argument(
        "--monitor-buffer-size",
        type=int,
        default=1000,
        help="Number of recent output chunks to buffer for new monitor clients (default: 1000)"
    )
    
    args = parser.parse_args()
    
    # Determine shell command
    shell_command = args.shell or os.environ.get("SHELL", "/bin/sh")
    
    # Validate shell exists and is executable
    if not os.path.isfile(shell_command) or not os.access(shell_command, os.X_OK):
        print(f"Error: Shell '{shell_command}' not found or not executable", file=sys.stderr)
        sys.exit(1)
    
    # Determine output file
    output_file = args.output or generate_output_filename()
    
    # Convert to absolute path
    output_path = Path(output_file).resolve()
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Recording session to: {output_path}")
    print(f"Shell: {shell_command}")
    if args.monitor:
        print(f"Monitor server will start on http://{args.monitor_host}:{args.monitor_port}")
    print("Press Ctrl+C or exit shell to stop recording\n")
    
    # Start recording
    recorder = AsciinemaRecorder(
        output_file=str(output_path), 
        shell_command=shell_command,
        monitor_enabled=args.monitor,
        monitor_host=args.monitor_host,
        monitor_port=args.monitor_port,
        monitor_buffer_size=args.monitor_buffer_size
    )
    recorder.record_session()
    
    print(f"\nRecording saved to: {output_path}")


if __name__ == "__main__":
    main()