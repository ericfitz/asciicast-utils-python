# CLAUDE.md

Python utilities for recording and preprocessing asciicast v2 terminal sessions. Standard library only (Python 3.8+); each script carries PEP 723 inline metadata so `uv run` works without a project.

## Running

```bash
uv run record_session.py                                    # default shell, auto-named output
uv run record_session.py --shell /bin/bash --output my.cast
python3 record_session.py --shell zsh                       # plain Python also works
```

## Architecture

**`record_session.py`** — `AsciinemaRecorder`. Forks a child under a PTY (`pty.openpty()` + `os.fork()`), multiplexes fds with `select.select()`, and writes asciicast v2: a JSON header (version, dimensions, timestamp, shell) followed by newline-delimited `[timestamp, "i"|"o", data]` events. Timestamps are rounded to 3 decimals; `termios` settings are saved and restored; Ctrl+C is forwarded to the child; terminal size is detected and applied to the PTY. Works on macOS and Linux.

**`consolidate_input.py`** — `InputConsolidator`. Accumulates per-keystroke `"i"` events into one `"c"` (command) record per typed line. Original events are preserved unchanged; the `"c"` record is appended after the flushing `"i"` event with the first keystroke's timestamp. Accumulation spans intervening non-`"i"` events (shell echo). Flush triggers: CR, LF, Ctrl+C, or end of file.
