# SPDX-License-Identifier: MIT
import logging, struct
from .core import FWFile

log = logging.getLogger("asahi_firmware.asmedia")

MAGIC = b"2214A_RCFG"

def extract_asmedia(kernel):
    try:
        off = kernel.index(MAGIC)
    except ValueError:
        raise Exception("Could not find ASMedia firmware")

    size = struct.unpack("<I", kernel[off + 0x2f:off + 0x33])[0]
    if size != 0x18000:
        raise Exception(f"Unexpected ASMedia firmware size {size:#x}")

    data = kernel[off + 0x33: off + 0x33 + size]

    yield FWFile("asmedia/asm2214a-apple.bin", data)
