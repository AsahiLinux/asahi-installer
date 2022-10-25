# SPDX-License-Identifier: MIT
import os.path, tarfile

class CPIO:
    DIR = 0o040755
    FILE = 0o100644

    def __init__(self, filename):
        self.fd = open(filename, "wb")
        self.closed = False
        self.dirs = set()
        self.inode = 1
        self.nlink = {}
        self.nlinkoff = {}
        self.inodemap = {}

    def cpio_hdr(self, name, mode, size, target=None):
        if target is not None:
            inode = self.inodemap[target]
            self.nlink[inode] += 1
            p = self.fd.tell()
            for i in self.nlinkoff[inode]:
                self.fd.seek(i)
                self.fd.write(b"%08x" % self.nlink[inode])
            self.fd.seek(p)
        else:
            inode = self.inode
            self.inode += 1
            self.nlink[inode] = 1
            self.nlinkoff[inode] = []

        self.inodemap[name] = inode

        p = self.fd.tell()
        if p & 3:
            self.fd.write(bytes(4 - (p & 3)))

        self.fd.write(b"070701")
        self.nlinkoff[inode].append(self.fd.tell() + 8 * 4)
        hdr = [
            inode,
            mode,
            0, # uid
            0, # gid
            self.nlink[inode],
            0, # mtime
            size,
            0, # maj
            0, # min
            0, # rmaj
            0, # rmin
            len(name) + 1,
            0, # chksum
        ]
        self.fd.write(b"".join(b"%08x" % i for i in hdr))
        self.fd.write(name.encode("ascii") + b"\x00")

        p = self.fd.tell()
        if p & 3:
            self.fd.write(bytes(4 - (p & 3)))
    
    def addfile(self, ti, fd):
        path = ""
        for i in ti.name.split("/")[:-1]:
            if not i:
                continue
            path = os.path.join(path, i)
            if path not in self.dirs:
                self.cpio_hdr(path, self.DIR, 0)
                self.dirs.add(path)

        if ti.type == tarfile.LNKTYPE:
            self.cpio_hdr(ti.name, self.FILE, 0, ti.linkname)
        elif ti.type == tarfile.REGTYPE:
            self.cpio_hdr(ti.name, self.FILE, ti.size)
            self.fd.write(fd.read())
        else:
            raise Exception(f"Unsupported file type {ti.type}")
    
    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cpio_hdr("TRAILER!!!", self.FILE, 0);    
        self.fd.close()
    
    def __del__(self):
        self.close()
