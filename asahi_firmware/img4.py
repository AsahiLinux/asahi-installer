# SPDX-License-Identifier: MIT
from . import asn1
from ctypes import *

__all__ = ["img4p_extract_compressed", "img4p_extract"]

def decode_lzfse(cdata, raw_size):
    lzfse = CDLL("liblzfse.so")

    dest = create_string_buffer(raw_size)
    decoded = lzfse.lzfse_decode_buffer(dest, raw_size, cdata, len(cdata), None)

    assert decoded == raw_size
    return dest.raw

def decode_header(decoder):
    tag = decoder.peek()
    assert tag.nr == asn1.Numbers.Sequence
    assert tag.typ == asn1.Types.Constructed
    decoder.enter()

    tag, value = decoder.read()
    assert tag == asn1.Tag(asn1.Numbers.IA5String, asn1.Types.Primitive, 0)
    assert value == "IM4P"

    tag, name = decoder.read()
    assert tag == asn1.Tag(asn1.Numbers.IA5String, asn1.Types.Primitive, 0)

    tag, unk = decoder.read()
    assert tag == asn1.Tag(asn1.Numbers.IA5String, asn1.Types.Primitive, 0)

    tag, data = decoder.read()
    assert tag == asn1.Tag(asn1.Numbers.OctetString, asn1.Types.Primitive, 0)

    return name, data

def img4p_extract_compressed(data):
    decoder = asn1.Decoder()
    decoder.start(data)
    name, cdata = decode_header(decoder)

    tag = decoder.peek()
    assert tag.nr == asn1.Numbers.Sequence
    assert tag.typ == asn1.Types.Constructed
    decoder.enter()

    tag, ctype = decoder.read()
    assert tag == asn1.Tag(asn1.Numbers.Integer, asn1.Types.Primitive, 0)
    assert ctype == 1

    tag, raw_size = decoder.read()
    assert tag == asn1.Tag(asn1.Numbers.Integer, asn1.Types.Primitive, 0)

    return name, decode_lzfse(cdata, raw_size)

def img4p_extract(data):
    decoder = asn1.Decoder()
    decoder.start(data)
    return decode_header(decoder)
