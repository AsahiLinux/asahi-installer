# SPDX-License-Identifier: MIT
import os, sys, os.path, time, logging
from dataclasses import dataclass

from urllib import request

@dataclass
class CacheBlock:
    idx: int
    data: bytes

class URLCache:
    CACHESIZE = 32
    BLOCKSIZE = 1 * 1024 * 1024
    READAHEAD = 10

    def __init__(self, url):
        self.url = url
        self.size = self.get_size()
        self.p = 0
        self.cache = {}
        self.blocks_read = 0

    def seekable(self):
        return True

    def get_size(self):
        req = request.Request(self.url, method="HEAD")
        fd = request.urlopen(req)
        return int(fd.getheader("Content-length"))

    def get_partial(self, off, size):
        #print("get_partial", off, size)
        req = request.Request(self.url, method="GET")
        req.add_header("Range", f"bytes={off}-{off+size-1}")
        fd = request.urlopen(req)

        if size <= self.BLOCKSIZE:
            sys.stdout.write(".")
        else:
            sys.stdout.write("+")
        sys.stdout.flush()
        self.blocks_read += 1

        return fd.read()

    def get_block(self, blk):
        logging.debug(f"get_block {blk}")

        if blk in self.cache:
            return self.cache[blk]

        off = blk * self.BLOCKSIZE
        size = self.BLOCKSIZE

        for i in range(self.READAHEAD):
            if blk + i in self.cache:
                break
            size += self.BLOCKSIZE

        size = min(off + size, self.size) - off
        retries = 5
        for retry in range(retries + 1):
            try:
                logging.debug(f"get_partial {off} {size}")
                data = self.get_partial(off, size)
            except Exception as e:
                if retry == retries:
                    print(f"Exceeded maximum retries downloading data.")
                    raise
                print(f"Error downloading data ({e}), retrying... ({retry + 1}/{retries})")
                time.sleep(1)
            else:
                break

        off = 0
        blk2 = blk

        while off < len(data):
            self.cache[blk2] = CacheBlock(idx=blk2, data=data[off:off + self.BLOCKSIZE])
            off += self.BLOCKSIZE
            blk2 += 1

        return self.cache[blk]

    def seek(self, offset, whence=os.SEEK_SET):
        if whence == os.SEEK_SET:
            self.p = offset
        elif whence == os.SEEK_END:
            self.p = self.size + offset
        elif whence == os.SEEK_CUR:
            self.p += offset

    def tell(self):
        return self.p

    def read(self, count=None):
        if count is None:
            count = self.size - self.p

        blk_start = self.p // self.BLOCKSIZE
        blk_end = (self.p + count - 1) // self.BLOCKSIZE

        d = []
        for blk in range(blk_start, blk_end + 1):
            d.append(self.get_block(blk).data)

        trim = self.p - (blk_start * self.BLOCKSIZE)
        d[0] = d[0][trim:]

        d = b"".join(d)[:count]
        assert len(d) == count
        self.p += count
        return d

    def flush_progress(self):
        if self.blocks_read > 0:
            sys.stdout.write("\n")
        self.blocks_read = 0


if __name__ == "__main__":
    import sys, zipfile

    url = sys.argv[1]
    zf = zipfile.ZipFile(URLCache(url))
    for f in zf.infolist():
        print(f)

    for i in sys.argv[2:]:
        dn = os.path.dirname(i)
        if dn:
            os.makedirs(dn, exist_ok=True)
        open(i,"wb").write(zf.open(i).read())
