# SPDX-License-Identifier: MIT
import re, logging, sys, os, stat, shutil, struct, subprocess, zlib, time, hashlib, lzma
from ctypes import *

if sys.platform == 'darwin':
    lzfse = CDLL('libcompression.dylib')
else:
    lzfse = None

COMPRESSION_LZFSE = 0x801
CHUNK_SIZE = 0x10000

DISTRO = os.environ.get("DISTRO", "Asahi Linux")
DISTRO_DOCS = os.environ.get("DISTRO_DOCS", "https://alx.sh/w")

def ssize(v):
    suffixes = ["B", "KB", "MB", "GB", "TB"]
    for i in suffixes:
        if v < 1000 or i == suffixes[-1]:
            if isinstance(v, int):
                return f"{v} {i}"
            else:
                return f"{v:.2f} {i}"
        v /= 1000

def psize(v, align=None):
    v = v.upper().replace(" ", "")
    base = 1000
    if v[-2] == "I":
        base = 1024
        v = v[:-2] + v[-1]
    suffixes = {"TB": 4, "GB": 3, "MB": 2, "KB": 1, "B": 0, "": 0}
    for suffix, power in suffixes.items():
        if v.endswith(suffix):
            val = int(float(v[:-len(suffix)]) * (base ** power))
            break
    else:
        return None
    if align is not None:
        if isinstance(align, str):
            align = psize(align)
            assert align is not None
        val = align_up(val, align)
    return val

def split_ver(s):
    parts = re.split(r"[-,. ]", s)
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

BLACK     = 30
RED       = 31
GREEN     = 32
YELLOW    = 33
BLUE      = 34
MAGENTA   = 35
CYAN      = 36
WHITE     = 37

BRIGHT    = 1
DIM       = 2
BLINK     = 5
NBLINK    = 25
NORMAL    = 22
RESET_ALL = 0

def col(*color):
    color = ";".join(map(str, color))
    return f"\033[{color}m"

def p_style(*args, color=[], **kwargs):
    if isinstance(color, int):
        color = [color]
    text = " ".join(map(str, args))
    print(col(*color) + text + col(), **kwargs)
    if "\033" in text:
        text += col()
    logging.info(f"MSG: {text}")

def p_plain(*args):
    p_style(*args)

def p_info(*args):
    p_style(*args, color=(BRIGHT, BLUE))

def p_progress(*args):
    p_style(*args, color=(BRIGHT, MAGENTA))

def p_message(*args):
    p_style(*args, color=BRIGHT)

def p_error(*args):
    p_style(*args, color=(BRIGHT, RED))

def p_warning(*args):
    p_style(*args, color=(BRIGHT, YELLOW))

def p_question(*args):
    p_style(*args, color=(BRIGHT, CYAN))

def p_success(*args):
    p_style(*args, color=(BRIGHT, GREEN))

def p_prompt(*args):
    p_style(*args, color=(BRIGHT, CYAN))

def p_choice(*args):
    p_style(*args)

def input_prompt(*args):
    while True:
        p_style(f"{col(BRIGHT, WHITE)}»{col(BRIGHT, CYAN)}", *args, end="")
        val = input()
        if any (ord(c) < 0x20 for c in val):
            p_error("Invalid input")
            continue
        break
    logging.info(f"INPUT: {val!r}")
    return val

class PBZX:
    def __init__(self, istream, osize):
        self.istream = istream
        self.osize = osize
        self.buf = b""
        self.p = 0
        self.total_read = 0

        hdr = istream.read(12)
        magic, blocksize = struct.unpack(">4sQ", hdr)
        assert magic == b"pbzx"

    def read(self, size):
        if (len(self.buf) - self.p) >= size:
            d = self.buf[self.p:self.p + size]
            self.p += len(d)
            return d

        bp = [self.buf[self.p:]]
        self.p = 0

        avail = len(bp[0])
        while avail < size and self.total_read < self.osize:
            hdr = self.istream.read(16)
            if not hdr:
                raise Exception("End of compressed data but more expected")

            uncompressed_size, compressed_size = struct.unpack(">QQ", hdr)
            blk = self.istream.read(compressed_size)
            if uncompressed_size != compressed_size:
                blk = lzma.decompress(blk, format=lzma.FORMAT_XZ)
            bp.append(blk)
            avail += len(blk)
            self.total_read += len(blk)

        self.buf = b"".join(bp)
        d = self.buf[self.p:self.p + size]
        self.p += len(d)
        return d

class PackageInstaller:
    def __init__(self):
        self.verbose = "-v" in sys.argv
        self.printed_progress = False

    def path(self, path):
        return path

    def flush_progress(self):
        if self.ucache and self.ucache.flush_progress():
            self.printed_progress = False
            return
        if self.printed_progress:
            sys.stdout.write("\n")
            self.printed_progress = False

    def extract(self, src, dest):
        dest_path = os.path.join(dest, src)
        dest_dir = os.path.split(dest_path)[0]
        os.makedirs(dest_dir, exist_ok=True)
        self.extract_file(src, dest_path)

    def fdcopy(self, sfd, dfd, size=None):
        BLOCK = 16 * 1024 * 1024
        copied = 0
        bps = 0
        st = time.time()
        if self.ucache:
            self.ucache.bytes_read = 0
        while True:
            if size is not None:
                prog = copied / size * 100
                sys.stdout.write(f"\033[3G{prog:6.2f}% ({ssize(bps)}/s)")
                sys.stdout.flush()
                self.printed_progress = True
            d = sfd.read(BLOCK)
            if not d:
                break
            dfd.write(d)
            copied += len(d)
            if self.ucache:
                bps = self.ucache.bytes_read / (time.time() - st)

        if size is not None:
            sys.stdout.write("\033[3G100.00% ")
            sys.stdout.flush()

    def copy_recompress(self, src, path):
        # For BXDIFF50 stuff in OTA images
        bxstream = self.pkg.open(src)
        assert bxstream.read(8) == b"BXDIFF50"
        bxstream.read(8)
        size, csize, zxsize = struct.unpack("<3Q", bxstream.read(24))
        assert csize == 0
        sha1 = bxstream.read(20)
        istream = PBZX(bxstream, size)
        self.stream_compress(istream, size, path, sha1=sha1)

    def copy_compress(self, src, path):
        info = self.pkg.getinfo(src)
        size = info.file_size
        istream = self.pkg.open(src)
        self.stream_compress(istream, size, path, crc=info.CRC)

    def stream_compress(self, istream, size, path, crc=None, sha1=None):
        with open(path, 'wb'):
            pass
        num_chunks = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
        cur_pos = (num_chunks + 1) * 4
        table = []
        scratch = bytes(lzfse.compression_encode_scratch_buffer_size(COMPRESSION_LZFSE))
        outbuf = bytes(CHUNK_SIZE)
        st = time.time()
        if self.ucache:
            self.ucache.bytes_read = 0
        copied = 0
        bps = 0
        with open(path + '/..namedfork/rsrc', 'wb') as res_fork:
            res_fork.write(b'\0' * cur_pos)
            for i in range(num_chunks):
                table.append(cur_pos)
                inbuf = istream.read(CHUNK_SIZE)
                copied += len(inbuf)
                prog = copied / size * 100
                if self.ucache:
                    bps = self.ucache.bytes_read / (time.time() - st)
                sys.stdout.write(f"\033[3G{prog:6.2f}% ({ssize(bps)}/s)")
                sys.stdout.flush()
                self.printed_progress = True
                while 1:
                    csize = lzfse.compression_encode_buffer(outbuf, len(outbuf), inbuf, len(inbuf), scratch, COMPRESSION_LZFSE)
                    if csize == 0:
                        outbuf = bytes(len(outbuf) * 2)
                    else:
                        break
                res_fork.write(outbuf[:csize])
                cur_pos += csize
            table.append(cur_pos)
            res_fork.seek(0)
            for v in table:
                res_fork.write(struct.pack('<I', v))
        subprocess.run(["xattr", "-wx", "com.apple.decmpfs",
                        "66706D630C000000" + "".join(f"{((size >> 8*i) & 0xff):02x}" for i in range(8)),
                        path], check=True)
        os.chflags(path, stat.UF_COMPRESSED)

        if sha1 is not None:
            sha = hashlib.sha1()
            with open(path, 'rb') as result_file:
                while 1:
                    data = result_file.read(CHUNK_SIZE)
                    if len(data) == 0:
                        break
                    sha.update(data)
            if sha.digest() != sha1:
                raise Exception('Internal error: failed to recompress file: SHA1 mismatch')
        elif crc is not None:
            calc_crc = 0
            with open(path, 'rb') as result_file:
                while 1:
                    data = result_file.read(CHUNK_SIZE)
                    if len(data) == 0:
                        break
                    calc_crc = zlib.crc32(data, calc_crc)
            if crc != calc_crc:
                raise Exception('Internal error: failed to compress file: crc mismatch')
        else:
            raise Exception("No checksum available")

        sys.stdout.write("\033[3G100.00% ")
        sys.stdout.flush()

    def extract_file(self, src, dest, optional=False):
        src = self.path(src)
        self._extract_file(src, dest, optional)

    def _extract_file(self, src, dest, optional=False):
        logging.info(f"  {src} -> {dest}")
        try:
            info = self.pkg.getinfo(src)
            with self.pkg.open(src) as sfd, \
                open(dest, "wb") as dfd:
                logging.info(f"  {src} -> {dest}")
                self.fdcopy(sfd, dfd, info.file_size)
        except KeyError:
            if not optional:
                raise
            logging.info(f"    (SKIPPED)")
        if self.verbose:
            self.flush_progress()

    def extract_tree(self, src, dest):
        src = self.path(src)
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
                self._extract_file(name, destpath)

            if self.verbose:
                self.flush_progress()
