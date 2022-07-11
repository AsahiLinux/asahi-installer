# SPDX-License-Identifier: MIT

from . import asn1

def img4p_extract(data):
    decoder = asn1.Decoder()
    decoder.start(data)
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
