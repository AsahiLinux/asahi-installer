# SPDX-License-Identifier: MIT
import os, sys, os.path, time, logging, random
from dataclasses import dataclass

from urllib import parse
from http.client import HTTPSConnection, HTTPConnection
from util import *

@dataclass
class CacheBlock:
    idx: int
    data: bytes

class URLCache:
    CACHESIZE = 128
    BLOCKSIZE = 1 * 1024 * 1024
    TIMEOUT = 30
    MIN_READAHEAD = 8
    MAX_READAHEAD = 64
    SPINNER = "/-\\|"

    def __init__(self, url):
        self.url_str = url
        self.url = parse.urlparse(url)
        self.con = None
        self.size = self.get_size()
        self.p = 0
        self.cache = {}
        self.blocks_read = 0
        self.bytes_read = 0
        self.readahead = self.MAX_READAHEAD
        self.spin = 0

    def close_connection(self):
        if self.con is not None:
            try:
                self.con.close()
            except Exception:
                pass
            self.con = None

    def get_con(self):
        if self.con is not None:
            return self.con

        if ":" in self.url.netloc:
            host, port = self.url.netloc.split(":")
            port = int(port)
        else:
            host, port = self.url.netloc, None

        if self.url.scheme == "http":
            self.con = HTTPConnection(host, port, timeout=self.TIMEOUT)
        elif self.url.scheme == "https":
            self.con = HTTPSConnection(host, port, timeout=self.TIMEOUT)
        else:
            raise Exception(f"Unsupported scheme {self.url.scheme}")

        return self.con

    def seekable(self):
        return True

    def get_size(self):
        con = self.get_con()
        con.request("HEAD", self.url.path, headers={"Connection":" keep-alive"})
        res = con.getresponse()
        res.read()
        return int(res.getheader("Content-length"))

    def get_partial(self, off, size, bypass_cache=False):
        path = self.url.path
        if bypass_cache:
            path += f"?{random.random()}"

        res = None
        try:
            con = self.get_con()
            con.request("GET", path, headers={
                "Connection": "keep-alive",
                "Range": f"bytes={off}-{off+size-1}",
            })
            res = con.getresponse()
            d = res.read()
        except Exception as e:
            logging.error(f"Request failed for {self.url_str} range {off}-{off+size-1}")
            if res is not None:
                logging.error(f"Response headers: {res.headers.as_string()}")
            raise

        self.spin = (self.spin + 1) % len(self.SPINNER)
        sys.stdout.write(f"\r{self.SPINNER[self.spin]} ")
        sys.stdout.flush()
        self.blocks_read += 1
        self.bytes_read += len(d)

        return d

    def get_block(self, blk, readahead=1):
        if blk in self.cache:
            return self.cache[blk]

        off = blk * self.BLOCKSIZE
        size = self.BLOCKSIZE

        blocks = max(self.MIN_READAHEAD,
                     min(readahead, self.readahead)) - 1

        for i in range(blocks):
            if blk + i in self.cache:
                break
            size += self.BLOCKSIZE

        size = min(off + size, self.size) - off
        retries = 10
        sleep = 1
        for retry in range(retries + 1):
            try:
                data = self.get_partial(off, size, bypass_cache=(retry == retries))
            except Exception as e:
                if retry == retries:
                    p_error(f"Exceeded maximum retries downloading data.")
                    raise
                p_warning(f"Error downloading data ({e}), retrying... ({retry + 1}/{retries})")
                time.sleep(sleep)
                self.close_connection()
                sleep += 1
                # Retry in smaller chunks after a couple errors
                if retry > 0:
                    self.readahead = self.MIN_READAHEAD
                size = min(size, self.readahead * self.BLOCKSIZE)
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

        blocks = blk_end - blk_start + 1

        d = []
        for blk in range(blk_start, blk_end + 1):
            readahead = blk_end - blk + 1
            d.append(self.get_block(blk, readahead).data)
            prog = (blk - blk_start + 1) / blocks * 100
            self.blocks_read += 1

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
            return True
        else:
            return False

if __name__ == "__main__":
    import sys, zipfile
    from util import PackageInstaller

    url = sys.argv[1]
    ucache = URLCache(url)
    zf = zipfile.ZipFile(ucache)

    pi = PackageInstaller()
    pi.ucache = ucache
    pi.pkg = zf

    for f in zf.infolist():
        print(f)

    for i in sys.argv[2:]:
        dn = os.path.dirname(i)
        if dn:
            os.makedirs(dn, exist_ok=True)
        pi.extract_file(i, i, False)
