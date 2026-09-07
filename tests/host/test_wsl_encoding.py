from host.providers.wsl_encoding import decode_wsl


def test_decodes_utf16le_meta_output():
    raw = "Ubuntu\r\ndocker-desktop\r\n".encode("utf-16-le")
    assert decode_wsl(raw) == "Ubuntu\ndocker-desktop"


def test_decodes_plain_utf8_passthrough():
    assert decode_wsl(b"HELLO-world\n") == "HELLO-world"


def test_empty_bytes_give_empty_string():
    assert decode_wsl(b"") == ""
