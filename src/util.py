# SPDX-License-Identifier: MIT
import re, logging, sys, os, stat, shutil

def ssize(v):
    suffixes = ["B", "KB", "MB", "GB", "TB"]
    for i in suffixes:
        if v < 1000 or i == suffixes[-1]:
            if isinstance(v, int):
                return f"{v} {i}"
            else:
                return f"{v:.2f} {i}"
        v /= 1000

def psize(v):
    v = v.upper()
    base = 1000
    if v[-2] == "i":
        base = 1024
        v = v[:-2] + v[-1]
    suffixes = {"TB": 4, "GB": 3, "MB": 2, "KB": 1, "B": 0, "": 0}
    for suffix, power in suffixes.items():
        if v.endswith(suffix):
            return int(float(v[:-len(suffix)]) * (base ** power))

def split_ver(s):
    parts = re.split(r"[-. ]", s)
    parts2 = []
    for i in parts:
        try:
            parts2.append(int(i))
        except ValueError:
            parts2.append(i)
    if len(parts2) > 3 and parts2[-2] == "beta":
        parts2[-3] -= 1
        parts2[-2] = 99
    return tuple(parts2)

def align_up(v, a=16384):
    return (v + a - 1) & ~(a - 1)

align = align_up

def align_down(v, a=16384):
    return v & ~(a - 1)

class PackageInstaller:
    def __init__(self):
        self.verbose = "-v" in sys.argv

    def flush_progress(self):
        if self.ucache:
            self.ucache.flush_progress()

    def extract(self, src, dest):
        logging.info(f"  {src} -> {dest}/")
        self.pkg.extract(src, dest)

    def extract_file(self, src, dest, optional=True):
        try:
            with self.pkg.open(src) as sfd, \
                open(dest, "wb") as dfd:
                logging.info(f"  {src} -> {dest}")
                shutil.copyfileobj(sfd, dfd)
        except KeyError:
            if not optional:
                raise
        if self.verbose:
            self.flush_progress()

    def extract_tree(self, src, dest):
        if src[-1] != "/":
            src += "/"
        logging.info(f"  {src}* -> {dest}")

        infolist = self.pkg.infolist()
        if self.verbose:
            self.flush_progress()

        for info in infolist:
            name = info.filename
            if not name.startswith(src):
                continue
            subpath = name[len(src):]
            assert subpath[0:1] != "/"

            destpath = os.path.join(dest, subpath)

            if info.is_dir():
                os.makedirs(destpath, exist_ok=True)
            elif stat.S_ISLNK(info.external_attr >> 16):
                link = self.pkg.open(info.filename).read()
                if os.path.lexists(destpath):
                    os.unlink(destpath)
                os.symlink(link, destpath)
            else:
                self.extract_file(name, destpath)

            if self.verbose:
                self.flush_progress()
