def decode_wsl(data: bytes) -> str:
    """wsl.exe meta commands emit UTF-16LE (NUL-interleaved); command
    passthrough emits UTF-8. Detect the former by embedded NUL bytes."""
    if not data:
        return ""
    if b"\x00" in data:
        text = data.decode("utf-16-le", "replace")
    else:
        text = data.decode("utf-8", "replace")
    return text.replace("\r\n", "\n").strip("\n").strip("\x00")
