from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Image:
    url: str
    sha256: str


# Canonical's official WSL images — the files Microsoft's WSL distribution
# manifest points at. cloud-images.ubuntu.com/wsl/ holds only manifests now.
WSL_IMAGES: dict[str, Image] = {
    "amd64": Image(
        "https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-wsl-amd64.wsl",
        "9b2f7730dc68227dd04a9f3e5eab86ad85caf556b8606ad94f1f29ff5c4fd3f5",
    ),
    "arm64": Image(
        "https://cdimages.ubuntu.com/releases/24.04.4/release/ubuntu-24.04.4-wsl-arm64.wsl",
        "6b244d89f412a68f51e58f396fab65bed3b5896a25c045a99bef9c78a07df507",
    ),
}
