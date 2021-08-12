# SPDX-License-Identifier: MIT
import re

def ssize(v):
    suffixes = ["B", "KB", "MB", "GB", "TB"]
    for i in suffixes:
        if v < 1000 or i == suffixes[-1]:
            if isinstance(v, int):
                return f"{v} {i}"
            else:
                return f"{v:.2f} {i}"
        v /= 1000

def split_ver(s):
    parts = re.split(r"[-.]", s)
    parts2 = []
    for i in parts:
        try:
            parts2.append(int(i))
        except ValueError:
            parts2.append(i)
    return tuple(parts2)
