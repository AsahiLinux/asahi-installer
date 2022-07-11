# SPDX-License-Identifier: MIT
import tarfile, io, logging
from hashlib import sha256

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
    def __init__(self, target):
        self.path = target
        self.tarfile = tarfile.open(target, mode="w")
        self.hashes = {}
        self.manifest = []

    def close(self):
        self.tarfile.close()

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

    def add_files(self, it):
        for name, data in it:
            self.add_file(name, data)

    def save_manifest(self, filename):
        with open(filename, "w") as fd:
            for i in self.manifest:
                fd.write(i + "\n")

    def __del__(self):
        self.tarfile.close()
