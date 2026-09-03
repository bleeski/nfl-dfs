from __future__ import annotations


def split_byte_lines(raw: bytes) -> tuple[bytes, ...]:
    """Split only on CSV physical-line LF bytes while retaining exact endings."""
    parts = raw.split(b"\n")
    lines = [part + b"\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return tuple(lines)


def split_line_ending(line: bytes) -> tuple[bytes, bytes]:
    if line.endswith(b"\r\n"):
        return line[:-2], b"\r\n"
    if line.endswith(b"\n"):
        return line[:-1], b"\n"
    return line, b""


def csv_field_spans(body: bytes) -> tuple[tuple[int, int], ...]:
    """Return byte spans for one physical CSV record without normalizing any field."""
    spans: list[tuple[int, int]] = []
    start = 0
    index = 0
    in_quotes = False
    while index < len(body):
        value = body[index]
        if value == 0x22:
            if in_quotes and index + 1 < len(body) and body[index + 1] == 0x22:
                index += 2
                continue
            in_quotes = not in_quotes
        elif value == 0x2C and not in_quotes:
            spans.append((start, index))
            start = index + 1
        index += 1
    if in_quotes:
        raise ValueError("unterminated quoted CSV field")
    spans.append((start, len(body)))
    return tuple(spans)
