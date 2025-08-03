#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///

# Copyright 2025 Eric Fitzgerald

import argparse
import json
import os
import pty
import select
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path
from typing import Dict, List, Tuple, Union


class AsciinemaPlayer:
    """Playbook for asciicast v2 files with support for custom 'e' (stderr) events."""
    
    def __init__(self, cast_file: str, speed: float = 1.0, max_delay: float = 5.0):
        self.cast_file = cast_file
        self.speed = speed
        self.max_delay = max_delay
        self.header: Dict = {}
        self.events: List[Tuple[float, str, str]] = []
        self.terminal_fd = None
        self.original_tty_settings = None
        self.paused = False
        self.skip_to_next = False
        self.base_title = f"Playing: {Path(cast_file).name}"
        
    def set_terminal_title(self, title: str) -> None:
        """Set the terminal window title using ANSI escape sequences.
        
        Writes to stderr instead of stdout to avoid interfering with the
        session output being played back. This keeps the playback clean
        while still providing status feedback in the window title.
        """
        # Use both OSC 0 (icon and title) and OSC 2 (title only) for compatibility
        # Write to stderr to avoid interfering with session output
        sys.stderr.write(f'\033]0;{title}\007')
        sys.stderr.write(f'\033]2;{title}\007')
        sys.stderr.flush()
        
    def load_cast_file(self) -> bool:
        """Load and parse the asciicast file."""
        try:
            with open(self.cast_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            if not lines:
                print(f"Error: Empty cast file: {self.cast_file}", file=sys.stderr)
                return False
                
            # Parse header (first line)
            try:
                self.header = json.loads(lines[0].strip())
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON in header: {e}", file=sys.stderr)
                return False
                
            # Validate header
            if self.header.get('version') != 2:
                print(f"Error: Unsupported asciicast version: {self.header.get('version')}", file=sys.stderr)
                return False
                
            # Parse events (remaining lines)
            for line_num, line in enumerate(lines[1:], 2):
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    event = json.loads(line)
                    if len(event) >= 3:
                        timestamp, event_type, data = event[0], event[1], event[2]
                        self.events.append((float(timestamp), str(event_type), str(data)))
                    else:
                        print(f"Warning: Malformed event at line {line_num}: {line}", file=sys.stderr)
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON at line {line_num}: {e}", file=sys.stderr)
                    
            print(f"Loaded {len(self.events)} events from {self.cast_file}")
            return True
            
        except FileNotFoundError:
            print(f"Error: Cast file not found: {self.cast_file}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Error loading cast file: {e}", file=sys.stderr)
            return False
            
    def create_terminal_window(self) -> bool:
        """Create a new terminal window for playback."""
        # Get terminal dimensions from header
        width = self.header.get('width', 80)
        height = self.header.get('height', 24)
        
        # Create absolute paths to avoid issues
        script_path = os.path.abspath(__file__)
        cast_path = os.path.abspath(self.cast_file)
        
        # Determine terminal command based on platform
        if sys.platform == 'darwin':  # macOS
            # Use a more robust AppleScript approach
            applescript = f'''
            tell application "Terminal"
                activate
                do script "cd '{os.path.dirname(script_path)}' && python3 '{script_path}' --play-in-terminal '{cast_path}' --speed {self.speed} --max-delay {self.max_delay}; echo ''; echo 'Playback finished. Press Enter to close...'; read"
            end tell
            '''
            
            terminal_commands = [
                ['osascript', '-e', applescript],
                # Fallback to open command
                ['open', '-a', 'Terminal', f"{script_path}", '--args', '--play-in-terminal', cast_path, '--speed', str(self.speed), '--max-delay', str(self.max_delay)]
            ]
        else:  # Linux and other Unix-like systems
            terminal_commands = [
                ['gnome-terminal', '--', 'python3', script_path, '--play-in-terminal', cast_path, '--speed', str(self.speed), '--max-delay', str(self.max_delay)],
                ['konsole', '-e', 'python3', script_path, '--play-in-terminal', cast_path, '--speed', str(self.speed), '--max-delay', str(self.max_delay)],
                ['xterm', '-e', f"python3 '{script_path}' --play-in-terminal '{cast_path}' --speed {self.speed} --max-delay {self.max_delay}; echo 'Press Enter to close...'; read"],
                ['x-terminal-emulator', '-e', f"python3 '{script_path}' --play-in-terminal '{cast_path}' --speed {self.speed} --max-delay {self.max_delay}"]
            ]
            
        # Try each terminal command
        for cmd in terminal_commands:
            try:
                result = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"Opened playback in new terminal window (PID: {result.pid})")
                return True
            except FileNotFoundError:
                continue
            except Exception as e:
                print(f"Failed to launch {cmd[0]}: {e}", file=sys.stderr)
                continue
                
        print("Error: Could not find a suitable terminal emulator", file=sys.stderr)
        print("Available terminal emulators:", file=sys.stderr)
        if sys.platform == 'darwin':
            print("  - Terminal.app (should be available by default)", file=sys.stderr)
        else:
            print("  - gnome-terminal, konsole, xterm, x-terminal-emulator", file=sys.stderr)
        return False
        
    def play_in_terminal(self) -> None:
        """Play the asciicast directly in the current terminal."""
        if not self.events:
            print("No events to play")
            return
            
        # Setup terminal
        self.setup_terminal()
        
        try:
            # Set initial title
            self.set_terminal_title(f"{self.base_title} - Ready to start")
            
            # Clear screen and show header info
            print("\033[2J\033[H", end='')  # Clear screen, move cursor to top
            print(f"Playing: {Path(self.cast_file).name}")
            print(f"Shell: {self.header.get('command', 'unknown')}")
            print(f"Dimensions: {self.header.get('width', 80)}x{self.header.get('height', 24)}")
            print(f"Speed: {self.speed}x")
            print(f"Max delay: {self.max_delay}s")
            print(f"Events: {len(self.events)}")
            print("\nControls during playback:")
            print("  - Space: Pause/unpause (status shown in title bar)")
            print("  - Tab: Skip to next input/marker and pause")
            print("  - Ctrl+C: Stop playback")
            print("\nPress any key to start...")
            
            # Wait for user input to start
            self.wait_for_keypress()
            
            # Clear screen for playback and set playing title
            print("\033[2J\033[H", end='')
            sys.stdout.flush()
            self.set_terminal_title(f"{self.base_title} - Playing")
            
            # Play events
            self.play_events()
            
        except KeyboardInterrupt:
            self.set_terminal_title(f"{self.base_title} - Interrupted")
            print("\n\nPlayback interrupted")
        finally:
            self.restore_terminal()
            self.set_terminal_title(f"{self.base_title} - Finished")
            print(f"\n\nPlayback finished: {Path(self.cast_file).name}")
            
    def setup_terminal(self) -> None:
        """Setup terminal for playback with responsive keyboard controls.
        
        Sets terminal to raw mode to capture all keyboard input without
        echo, preventing control keys (Space, Tab) from appearing in
        the session output while enabling immediate response to controls.
        """
        if os.isatty(sys.stdin.fileno()):
            self.original_tty_settings = termios.tcgetattr(sys.stdin.fileno())
            # Set terminal to raw mode to capture all keyboard input without echo
            tty.setraw(sys.stdin.fileno())
            
    def restore_terminal(self) -> None:
        """Restore original terminal settings."""
        if self.original_tty_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.original_tty_settings)
            
    def wait_for_keypress(self) -> None:
        """Wait for user to press a key."""
        if os.isatty(sys.stdin.fileno()):
            # Terminal is already in raw mode from setup_terminal()
            sys.stdin.read(1)
                    
    def handle_input_during_playback(self) -> bool:
        """Handle keyboard input during playback. Returns True to continue, False to stop."""
        if select.select([sys.stdin], [], [], 0)[0]:
            if os.isatty(sys.stdin.fileno()):
                try:
                    char = sys.stdin.read(1)
                    if not char:  # EOF
                        return True
                        
                    char_code = ord(char)
                    
                    if char_code == 3:  # Ctrl+C
                        raise KeyboardInterrupt
                    elif char_code == 32:  # Space - pause/unpause
                        self.paused = not self.paused
                        if self.paused:
                            self.set_terminal_title(f"{self.base_title} - PAUSED (Space: continue, Tab: skip to next input)")
                        else:
                            self.set_terminal_title(f"{self.base_title} - Playing")
                        return True  # Consume the input to prevent space appearing in session
                    elif char_code == 9:  # Tab - skip to next input/marker
                        self.skip_to_next = True
                        if not self.paused:
                            self.set_terminal_title(f"{self.base_title} - Skipping to next marker/input...")
                        return True  # Consume the input to prevent tab appearing in session
                    else:
                        # Consume all other keys to prevent them from contaminating session output
                        # This ensures only the actual recorded session content is displayed
                        return True
                        
                except OSError:
                    # Handle potential read errors gracefully
                    pass
        return True
        
    def wait_while_paused(self) -> None:
        """Wait while paused, handling input."""
        while self.paused:
            time.sleep(0.1)
            try:
                self.handle_input_during_playback()
            except KeyboardInterrupt:
                raise
                
    def find_next_marker_or_input_event(self, current_index: int) -> int:
        """Find the index of the next marker or input event after current_index."""
        for i in range(current_index + 1, len(self.events)):
            event_type = self.events[i][1]
            event_data = self.events[i][2]
            # Look for input events or activity resumption markers
            if event_type == 'i' or (event_type == 'm' and 'activity_resumed_after' in event_data):
                return i
        return len(self.events)  # No more markers or input events
        
    def play_events(self) -> None:
        """Play back the recorded events with timing."""
        last_timestamp = 0.0
        
        for event_index, (timestamp, event_type, data) in enumerate(self.events):
            # Handle pause state
            if self.paused:
                self.wait_while_paused()
            
            # Handle skip to next input or activity marker
            # This allows Tab navigation to jump between user commands and natural pause points
            if self.skip_to_next:
                # Stop at user input events or activity resumption markers (5+ second gaps)
                if (event_type == 'i' or 
                    (event_type == 'm' and 'activity_resumed_after' in data)):
                    self.skip_to_next = False
                    self.paused = True
                    if event_type == 'i':
                        self.set_terminal_title(f"{self.base_title} - PAUSED at next input (Space: continue)")
                    else:
                        # Extract gap duration from marker data for user feedback
                        gap_info = data.replace('activity_resumed_after_', '').replace('s', '')
                        self.set_terminal_title(f"{self.base_title} - PAUSED after {gap_info}s gap (Space: continue)")
                    self.wait_while_paused()
                elif event_type in ['o', 'e']:  # Skip delay for output events when skipping
                    # Don't delay when skipping to next input
                    pass
                else:
                    # For other events, still apply normal timing
                    pass
            else:
                # Normal timing when not skipping
                delay = (timestamp - last_timestamp) / self.speed
                if delay > 0:
                    # Cap the delay to avoid extremely long pauses
                    capped_delay = min(delay, self.max_delay)
                    if delay > self.max_delay:
                        # Show skip message in title
                        self.set_terminal_title(f"{self.base_title} - Skipping {delay:.1f}s pause -> {self.max_delay:.1f}s")
                        # Brief pause to show the message, then restore normal title
                        time.sleep(0.5)
                        self.set_terminal_title(f"{self.base_title} - Playing")
                    
                    # Sleep in small chunks to be responsive to input
                    remaining_delay = capped_delay
                    while remaining_delay > 0 and not self.paused and not self.skip_to_next:
                        sleep_time = min(0.1, remaining_delay)
                        time.sleep(sleep_time)
                        remaining_delay -= sleep_time
                        
                        # Check for input during delay
                        try:
                            self.handle_input_during_playback()
                        except KeyboardInterrupt:
                            raise
                            
                        # If paused during delay, wait
                        if self.paused:
                            self.wait_while_paused()
                
            # Handle different event types
            if event_type == 'o':  # stdout
                # Write to stdout but don't flush immediately to allow input capture
                sys.stdout.write(data)
                sys.stdout.flush()
            elif event_type == 'e':  # stderr (custom event type)
                # Write stderr to stderr 
                sys.stderr.write(data)
                sys.stderr.flush()
            elif event_type == 'i':  # stdin (typically not played back)
                pass
            elif event_type == 'r':  # resize event
                # Parse resize data (format: "height,width")
                try:
                    if ',' in data:
                        height, width = map(int, data.split(','))
                        # Send resize escape sequence
                        sys.stdout.write(f'\033[8;{height};{width}t')
                        sys.stdout.flush()
                except ValueError:
                    pass
            elif event_type == 'm':  # metadata event
                # Skip metadata events during playback
                pass
            else:
                # Handle unknown event types gracefully
                print(f"Unknown event type: {event_type}", file=sys.stderr)
                
            last_timestamp = timestamp
            
            # Check for general input
            try:
                self.handle_input_during_playback()
            except KeyboardInterrupt:
                raise


def show_help():
    """Display detailed help information."""
    help_text = """
asciicast Playback Utility

SYNTAX:
    python3 playback_session.py [OPTIONS] <cast_file>
    uv run playback_session.py [OPTIONS] <cast_file>

DESCRIPTION:
    Plays back terminal sessions recorded in asciicast v2 format.
    Supports standard 'i' (input), 'o' (output) events and custom 'e' (stderr) events.
    
    When a .cast file is provided, the utility opens a new terminal window
    and plays back the recorded session with original timing.

OPTIONS:
    --speed FACTOR     Playback speed multiplier (default: 1.0)
                      - 0.5 = half speed (slower)
                      - 2.0 = double speed (faster)
    
    --max-delay SECONDS  Maximum delay between events in seconds (default: 5.0)
                         Long pauses are capped to this value to avoid waiting
    
    --play-in-terminal   Play directly in current terminal (internal use)
    
    -h, --help          Show this help message

EXAMPLES:
    # Play a recorded session at normal speed
    python3 playback_session.py my_session.cast
    
    # Play at double speed
    python3 playback_session.py --speed 2.0 my_session.cast
    
    # Play at half speed for detailed viewing
    python3 playback_session.py --speed 0.5 slow_demo.cast
    
    # Cap long pauses at 2 seconds
    python3 playback_session.py --max-delay 2.0 my_session.cast
    
    # Using uv (if available)
    uv run playback_session.py recording_20250103_143022.cast

ASCIICAST FORMAT:
    This utility supports asciicast v2 format with the following event types:
    - 'o': Standard output (stdout)
    - 'e': Error output (stderr) - custom extension
    - 'i': Input (stdin) - displayed but not interactive
    - 'r': Terminal resize events
    - 'm': Metadata events and activity markers (auto-inserted after 5s+ gaps)

PLATFORM SUPPORT:
    - macOS: Uses Terminal.app via AppleScript
    - Linux: Supports gnome-terminal, konsole, xterm, x-terminal-emulator

CONTROLS:
    Before playback:
    - Press any key to start playback
    
    During playback:
    - Space: Pause/unpause playback (status shown in terminal title)
    - Tab: Skip to next input event or activity marker and pause
    - Ctrl+C: Stop playback immediately
    
    Status messages appear in the terminal window title bar, keeping the 
    playback output clean and uninterrupted.
    """
    print(help_text)


def main():
    # Show help if no arguments provided
    if len(sys.argv) == 1:
        show_help()
        return
        
    parser = argparse.ArgumentParser(
        description="Play back asciicast v2 terminal recordings",
        add_help=False  # We'll handle help ourselves
    )
    
    parser.add_argument('cast_file', nargs='?', help='Asciicast file to play')
    parser.add_argument('--speed', type=float, default=1.0, 
                       help='Playback speed multiplier (default: 1.0)')
    parser.add_argument('--max-delay', type=float, default=5.0,
                       help='Maximum delay between events in seconds (default: 5.0)')
    parser.add_argument('--play-in-terminal', action='store_true',
                       help='Play in current terminal (internal use)')
    parser.add_argument('-h', '--help', action='store_true',
                       help='Show help message')
    
    args = parser.parse_args()
    
    # Handle help
    if args.help or not args.cast_file:
        show_help()
        return
        
    # Validate cast file
    if not os.path.isfile(args.cast_file):
        print(f"Error: Cast file not found: {args.cast_file}", file=sys.stderr)
        sys.exit(1)
        
    # Validate speed
    if args.speed <= 0:
        print(f"Error: Speed must be positive, got: {args.speed}", file=sys.stderr)
        sys.exit(1)
        
    # Validate max_delay
    if args.max_delay <= 0:
        print(f"Error: Max delay must be positive, got: {args.max_delay}", file=sys.stderr)
        sys.exit(1)
        
    # Create player instance
    player = AsciinemaPlayer(args.cast_file, args.speed, args.max_delay)
    
    # Load the cast file
    if not player.load_cast_file():
        sys.exit(1)
        
    # Play in current terminal or create new window
    if args.play_in_terminal:
        player.play_in_terminal()
    else:
        if not player.create_terminal_window():
            print("\nFalling back to playback in current terminal...", file=sys.stderr)
            print("Press Enter to continue...", end='')
            input()
            player.play_in_terminal()


if __name__ == "__main__":
    main()