"""Readable failures for the library UI, including captured subprocess output."""

import re
import shlex
import subprocess


def describe_error(error: Exception) -> str:
    def text(value) -> str:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(value or "")).strip()

    parts = []
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, subprocess.CalledProcessError):
            output = text(current.stderr)
            if not output and isinstance(current.stdout, str):
                output = text(current.stdout)
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            reason = next(
                (line for line in reversed(lines) if re.search(r"\b(error|fatal)\b", line, re.I)),
                lines[-1] if lines else "Process failed without captured error output",
            )
            command = current.cmd
            if isinstance(command, (list, tuple)):
                command = shlex.join(str(arg) for arg in command)
            parts.append(
                f"{reason}\nCalledProcessError (exit {current.returncode})"
                + (f"\n\nProcess output:\n{output[-12000:]}" if output else "")
                + f"\n\nCommand: {str(command)[:2000]}"
            )
        else:
            parts.append(f"{type(current).__name__}: {text(current) or 'No exception message'}")
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    return "\n\nCaused by:\n".join(parts)[:24000]
