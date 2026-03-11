#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///

# Copyright 2025 Eric Fitzgerald

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

# Characters that trigger flushing the accumulated input buffer
FLUSH_CHARS = {"\r", "\n", "\x03"}  # CR, LF, Ctrl+C


class InputConsolidator:
    """Consolidates scattered per-keystroke input events into command line records.

    Input events in asciicast files are typically individual keystrokes interleaved
    with output events (shell echo). This class accumulates input across intervening
    non-input events and appends a "c" (command) record for each typed line.

    All original events are preserved unchanged. The "c" records are a new event
    type that won't interfere with existing asciicast tools.
    """

    def __init__(self, cast_file: str):
        self.cast_file = cast_file
        self.header: Dict = {}
        self.events: List[Tuple[float, str, str]] = []

    def load_cast_file(self) -> bool:
        """Load and parse the asciicast file."""
        try:
            with open(self.cast_file, "r", encoding="utf-8") as f:
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
            if self.header.get("version") != 2:
                print(
                    f"Error: Unsupported asciicast version: {self.header.get('version')}",
                    file=sys.stderr,
                )
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
                        self.events.append(
                            (float(timestamp), str(event_type), str(data))
                        )
                    else:
                        print(
                            f"Warning: Malformed event at line {line_num}: {line}",
                            file=sys.stderr,
                        )
                except json.JSONDecodeError as e:
                    print(
                        f"Warning: Invalid JSON at line {line_num}: {e}",
                        file=sys.stderr,
                    )

            print(
                f"Loaded {len(self.events)} events from {self.cast_file}",
                file=sys.stderr,
            )
            return True

        except FileNotFoundError:
            print(f"Error: Cast file not found: {self.cast_file}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Error loading cast file: {e}", file=sys.stderr)
            return False

    def consolidate(self) -> Tuple[Dict, List]:
        """Consolidate scattered input events into "c" (command) records.

        All original events are preserved unchanged. Accumulates "i" event data
        across intervening non-"i" events and appends a "c" record at the position
        of each flush-triggering "i" event, using the timestamp of the first
        keystroke in the accumulated sequence.
        """
        accumulated_input = ""
        first_input_timestamp: Optional[float] = None
        output_events: List[List] = []

        for timestamp, event_type, data in self.events:
            # All original events pass through unchanged
            output_events.append([timestamp, event_type, data])

            if event_type == "i":
                # Start tracking timestamp from first keystroke
                if not accumulated_input:
                    first_input_timestamp = timestamp

                accumulated_input += data

                # Check if any flush character is present in the data
                if any(ch in data for ch in FLUSH_CHARS):
                    output_events.append(
                        [first_input_timestamp, "c", accumulated_input]
                    )
                    accumulated_input = ""
                    first_input_timestamp = None

        # Flush any remaining accumulated input at end of file
        if accumulated_input and first_input_timestamp is not None:
            output_events.append([first_input_timestamp, "c", accumulated_input])

        return (self.header, output_events)

    def write_output(self, output_file: Optional[str]) -> None:
        """Consolidate and write output to file or stdout."""
        header, events = self.consolidate()

        if output_file:
            out = open(output_file, "w", encoding="utf-8")
        else:
            out = sys.stdout

        try:
            out.write(json.dumps(header) + "\n")
            for event in events:
                out.write(json.dumps(event) + "\n")
        finally:
            if output_file:
                out.close()


def show_help():
    """Display detailed help information."""
    help_text = """
asciicast Input Consolidation Utility

SYNTAX:
    python3 consolidate_input.py [OPTIONS] <cast_file>
    uv run consolidate_input.py [OPTIONS] <cast_file>

DESCRIPTION:
    Preprocesses asciicast v2 files by consolidating scattered per-keystroke
    input ("i") events into "c" (command) records representing complete
    typed command lines.

    During recording, each keystroke is captured as a separate "i" event,
    often interleaved with output ("o") events from shell echo. This tool
    accumulates those keystrokes and appends a "c" record for each complete
    line, making the file easier to analyze and review.

    All original events are preserved unchanged. The "c" records are
    appended after the line-terminating keystroke, using the timestamp of
    the first keystroke in the sequence. This avoids losing information
    or confusing existing asciicast tools.

OPTIONS:
    -o, --output FILE   Write output to FILE instead of stdout

    -h, --help          Show this help message

FLUSH TRIGGERS:
    Input is accumulated until one of these characters appears:
    - Carriage return (\\r) - Enter key
    - Newline (\\n)
    - Ctrl+C (ETX, 0x03)

    Special characters like backspace, escape sequences, and tab are
    preserved as-is in the consolidated record.

EXAMPLES:
    # Consolidate input and print to stdout
    python3 consolidate_input.py session.cast

    # Consolidate input and write to a new file
    python3 consolidate_input.py -o consolidated.cast session.cast

    # Using uv
    uv run consolidate_input.py recording_20250103_143022.cast

    # Pipe to extract just the consolidated command lines
    uv run consolidate_input.py session.cast | grep '"c"'
    """
    print(help_text)


def main():
    # Show help if no arguments provided
    if len(sys.argv) == 1:
        show_help()
        return

    parser = argparse.ArgumentParser(
        description="Consolidate scattered input events in asciicast v2 files",
        add_help=False,
    )

    parser.add_argument("cast_file", nargs="?", help="Asciicast file to process")
    parser.add_argument(
        "-o",
        "--output",
        help="Output file path (default: stdout)",
    )
    parser.add_argument("-h", "--help", action="store_true", help="Show help message")

    args = parser.parse_args()

    # Handle help
    if args.help or not args.cast_file:
        show_help()
        return

    # Validate cast file
    if not os.path.isfile(args.cast_file):
        print(f"Error: Cast file not found: {args.cast_file}", file=sys.stderr)
        sys.exit(1)

    # Create consolidator and process
    consolidator = InputConsolidator(args.cast_file)

    if not consolidator.load_cast_file():
        sys.exit(1)

    consolidator.write_output(args.output)

    if args.output:
        print(f"Consolidated output written to: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
