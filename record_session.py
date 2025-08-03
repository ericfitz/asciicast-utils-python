#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///

import argparse
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
import time
import tty
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO


class AsciinemaRecorder:
    def __init__(self, output_file: str, shell_command: str):
        self.output_file = output_file
        self.shell_command = shell_command
        self.start_time = time.time()
        self.cast_file: Optional[TextIO] = None
        self.original_tty_settings = None
        self.last_terminal_attrs = None
        self.last_winsize = None
        
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
        """Write an event to the asciicast file."""
        if self.cast_file:
            timestamp = round(time.time() - self.start_time, 3)
            event = [timestamp, event_type, data]
            self.cast_file.write(json.dumps(event) + '\n')
            self.cast_file.flush()
    
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
    print("Press Ctrl+C or exit shell to stop recording\n")
    
    # Start recording
    recorder = AsciinemaRecorder(str(output_path), shell_command)
    recorder.record_session()
    
    print(f"\nRecording saved to: {output_path}")


if __name__ == "__main__":
    main()