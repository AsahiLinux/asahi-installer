# SPDX-License-Identifier: MIT
import struct, os, logging
from .img4 import img4p_extract
from .core import FWFile
from .asmedia import extract_asmedia

log = logging.getLogger("asahi_firmware.kernel")

class KernelFWCollection(object):
    def __init__(self, source_path):
        self.fwfiles = []
        self.load(source_path)

    def load(self, source_path):
        if os.path.isdir(source_path):
            for fname in os.listdir(source_path):
                if fname.startswith("kernelcache"):
                    kern_path = os.path.join(source_path, fname)
                    break
            else:
                raise Exception("Could not find kernelcache")
        else:
            kern_path = source_path

        log.info(f"Extracting firmware from kernel at {kern_path}")

        with open(kern_path, "rb") as fd:
            im4p = fd.read()
        name, kernel = img4p_extract(im4p)

        for fwf in extract_asmedia(kernel):
            self.fwfiles.append((fwf.name, fwf))

    def files(self):
        return self.fwfiles

