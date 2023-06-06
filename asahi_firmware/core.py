# SPDX-License-Identifier: MIT
import tarfile, io, logging, os.path
from hashlib import sha256
from . import cpio

UBOOT_FILES = set([
    "asmedia/asm2214a-apple.bin"
])

class FWFile(object):
    def __init__(self, name, data):
        self.name = name
        self.data = data
        self.sha = sha256(data).hexdigest()

    def __repr__(self):
        return f"FWFile({self.name!r}, <{self.sha[:16]}>)"

    def __eq__(self, other):
        if other is None:
            return False
        return self.sha == other.sha

    def __hash__(self):
        return hash(self.sha)

class FWPackage(object):
    def __init__(self, path):
        self.closed = False
        self.path = path
        self.tar_path = os.path.join(path, "firmware.tar")
        self.cpio_path = os.path.join(path, "firmware.cpio")
        self.tarfile = tarfile.open(self.tar_path, mode="w")
        self.cpiofile = cpio.CPIO(self.cpio_path)
        self.hashes = {}
        self.manifest = []

    def close(self):
        if self.closed:
            return

        self.closed = True

        ti = tarfile.TarInfo("vendorfw/.vendorfw.manifest")
        ti.type = tarfile.REGTYPE
        fd = io.BytesIO()
        for i in self.manifest:
            fd.write(i.encode("ascii") + b"\n")
        ti.size = fd.tell()
        fd.seek(0)
        self.cpiofile.addfile(ti, fd)

        self.tarfile.close()
        self.cpiofile.close()

        with open(os.path.join(self.path, "manifest.txt"), "w") as fd:
            for i in self.manifest:
                fd.write(i + "\n")

    def add_file(self, name, data):
        ti = tarfile.TarInfo(name)
        fd = None
        if data.sha in self.hashes:
            ti.type = tarfile.LNKTYPE
            ti.linkname = self.hashes[data.sha]
            self.manifest.append(f"LINK {name} {ti.linkname}")
        else:
            ti.type = tarfile.REGTYPE
            ti.size = len(data.data)
            fd = io.BytesIO(data.data)
            self.hashes[data.sha] = name
            self.manifest.append(f"FILE {name} SHA256 {data.sha}")

        logging.info(f"+ {self.manifest[-1]}")
        self.tarfile.addfile(ti, fd)
        if fd is not None:
            fd.seek(0)
        ti.name = os.path.join("vendorfw", ti.name)
        if ti.linkname:
            ti.linkname = os.path.join("vendorfw", ti.linkname)
        self.cpiofile.addfile(ti, fd)

        if name in UBOOT_FILES:
            path = os.path.join(self.path, "u-boot", name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fd:
                fd.write(data.data)

    def add_files(self, it):
        for name, data in it:
            self.add_file(name, data)

    def __del__(self):
        self.close()
