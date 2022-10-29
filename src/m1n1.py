# SPDX-License-Identifier: MIT

def build(src, dest, vars):
    if isinstance(vars, (list, tuple)):
        vars = b"".join(i.encode("ascii") + b"\n" for i in vars) + b"\0\0\0\0"

    with open(src, "rb") as fd:
        m1n1_data = fd.read()

    with open(dest, "wb") as fd:
        fd.write(m1n1_data + vars)

def extract_vars(src):
    with open(src, "rb") as fd:
        m1n1_data = fd.read()

    try:
        vars = m1n1_data.split(b"STACKBOT")[1].split(b"\0")[0].decode("ascii")
    except Exception:
        return None

    return [i for i in vars.split("\n") if i]

def get_version(path):
    data = open(path, "rb").read()
    if b"##m1n1_ver##" in data:
        return data.split(b"##m1n1_ver##")[1].split(b"\0")[0].decode("ascii")
    else:
        return None
