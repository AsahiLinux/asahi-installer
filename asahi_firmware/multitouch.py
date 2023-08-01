# SPDX-License-Identifier: MIT
import xml.etree.ElementTree as ET
import plistlib, base64, struct, os, logging
from .img4 import img4p_extract
from .core import FWFile

log = logging.getLogger("asahi_firmware.multitouch")

def load_plist_xml(d):
    root = ET.fromstring(d.decode("ascii"))

    idmap = {}
    def unmunge(el, idmap):
        if "ID" in el.attrib:
            idmap[el.attrib["ID"]] = el
        if "IDREF" in el.attrib:
            return idmap[el.attrib["IDREF"]]
        else:
            el2 = ET.Element(el.tag)
            el2.text = el.text
            el2.tag = el.tag
            el2.attrib = el.attrib
            for child in el:
                el2.append(unmunge(child, idmap))

            return el2
    pl = ET.Element("plist")
    pl.append(unmunge(root, idmap))

    return plistlib.loads(ET.tostring(pl))

LOAD_COMMAND_INIT_PAYLOAD = 0
LOAD_COMMAND_SEND_BLOB = 1
LOAD_COMMAND_SEND_CALIBRATION = 2

def plist_to_bin_touchbar(plist):
    def serialize(plist):
        yield struct.pack("<4sI", b"Z2FW", 1)
        for i in plist:
            if i["Type"] == "Config":
                init = i["Config"]["SPI Config"]["Init Payload"]
                yield struct.pack("<II", LOAD_COMMAND_INIT_PAYLOAD, len(init))
                yield init
                realign = len(init) % 4
                if realign != 0:
                    yield bytes([0] * (4 - realign))
        for i in plist:
            pkt_len = 0
            if i['Type'] == 'Binary':
                payload = i['Payload']
                pkt_len = 14 + len(payload)
                yield struct.pack("<II", LOAD_COMMAND_SEND_BLOB, pkt_len)
                addr = i['Address']
                hdr = struct.pack("<HHI", 0x3001, (len(payload) + 3) // 4, addr)
                yield hdr
                yield struct.pack("<H", sum(hdr[2:]))
                yield payload
                checksum = sum(payload)
                yield struct.pack("<I", checksum)
            elif i['Type'] == 'Property':
                yield struct.pack("<II", LOAD_COMMAND_SEND_CALIBRATION, i['Address'])
            elif i['Type'] == 'RequestCalibration':
                pkt_len = 2
                yield struct.pack("<II", LOAD_COMMAND_SEND_BLOB, pkt_len)
                yield struct.pack("<H", 0x1f01)
            elif i['Type'] == 'ReadModifyWrite':
                pkt_len = 16
                yield struct.pack("<II", LOAD_COMMAND_SEND_BLOB, pkt_len)
                data = struct.pack("<HIII", 0x1e33, i['Address'], i['Mask'], i['Value'])
                yield data
                yield struct.pack("<H", sum(data[2:]))
            realign = pkt_len % 4
            if realign != 0:
                yield bytes([0] * (4 - realign))
    return b"".join(serialize(plist))


def plist_to_bin_trackpad(plist):
    iface_offset = None

    for i in plist:
        if i["Type"] == "Config":
            for j in i["Config"]["Interface Config"]:
                if "HIDRecorder Descriptor" in j.keys():
                    continue
                j["bInterfaceNumber"] = None

    def serialize(o):
        if o is None:
            yield None
        elif o is True:
            yield bytes([0xf5])
        elif isinstance(o, dict):
            l = len(o)
            if l < 0x10:
                yield bytes([0xa0 + l])
            else:
                raise Exception("Unsupported serializer case")
                yield b"?"
            for k, v in o.items():
                yield from serialize(k)
                yield from serialize(v)
        elif isinstance(o, list):
            l = len(o)
            if l < 0x18:
                yield bytes([0x80 + l])
            else:
                raise Exception("Unsupported serializer case")
                yield b"?"
            for v in o:
                yield from serialize(v)
        elif isinstance(o, str):
            o = o.encode("utf-8") + b"\0"
            l = len(o)
            if l < 0x18:
                yield bytes([0x60 + l])
            elif l <= 0xff:
                yield bytes([0x78, l])
            else:
                raise Exception("Unsupported serializer case")
                yield b"?"
            yield o
        elif isinstance(o, int):
            if o < 0x18:
                yield bytes([o])
            elif o <= 0xff:
                yield bytes([0x18, o])
            elif o <= 0xffff:
                yield bytes([0x19])
                yield struct.pack(">H", o)
            else:
                yield bytes([0x1a])
                yield struct.pack(">I", o)
        elif isinstance(o, bytes):
            if len(o) <= 0xffff:
                yield (4, 3)
                yield struct.pack(">BH", 0x59, len(o))
            else:
                raise Exception("Unsupported serializer case")
                yield b"?" + struct.pack(">I", len(o))
            yield o
        else:
            raise Exception("Unsupported serializer case")
            yield b"?" + str(type(o)).encode("ascii")

    def add_padding(l):
        nonlocal iface_offset
        off = 0
        for b in l:
            if b is None:
                assert iface_offset is None
                iface_offset = off
                b = b"\x00"
            if isinstance(b, tuple):
                align, i = b
                if (off + i) % align != 0:
                    pad = align - ((off + i) % align)
                    off += pad
                    yield b"\xd3" * pad
            else:
                off += len(b)
                yield b

    blob = b"".join(add_padding(serialize(plist)))

    assert iface_offset is not None

    hdr = struct.pack("<4sIII", b"HIDF", 1, 32, len(blob))
    hdr += struct.pack("<I12x", iface_offset)
    assert len(hdr) == 32

    return hdr + blob

DEVICE_KIND_TRACKPAD = "trackpad"
DEVICE_KIND_TOUCHBAR = "touchbar"
DEVICE_KIND_UNKNOWN = "unknown"

def device_key_to_kind(key):
    if key.startswith("C1FD"):
        return DEVICE_KIND_TRACKPAD
    if key.startswith("C1FB"):
        return DEVICE_KIND_TOUCHBAR
    return DEVICE_KIND_UNKNOWN

FIRMWARE_NAME_TEMPLATES = {
    DEVICE_KIND_TRACKPAD: "apple/tpmtfw-%s.bin",
    DEVICE_KIND_TOUCHBAR: "apple/dfrmtfw-%s.bin"
}

plist_to_bin = {
    DEVICE_KIND_TRACKPAD: plist_to_bin_trackpad,
    DEVICE_KIND_TOUCHBAR: plist_to_bin_touchbar
}

class MultitouchFWCollection(object):
    def __init__(self, source_path):
        self.fwfiles = []
        self.load(source_path)

    def load(self, source_path):
        if not os.path.exists(source_path):
            #log.warning("fud_firmware is missing. You may need to update your stub with the Asahi Linux installer for Touch Bar functionality.")
            return

        for fname in os.listdir(source_path):
            if fname.startswith("j"):
                self.do_machine(fname, os.path.join(source_path, fname))

    def do_machine(self, machine, path):
        mtfw = os.path.join(path, "Multitouch.im4p")
        if not os.path.exists(mtfw):
            return

        log.info(f"Processing {machine}")

        with open(mtfw, "rb") as fd:
            im4p = fd.read()

        name, xml = img4p_extract(im4p)

        assert name == "mtfw"

        plist = load_plist_xml(xml.rstrip(b"\x00"))

        collected = set()
        for key, val in plist.items():
            dev_kind = device_key_to_kind(key)
            if dev_kind == DEVICE_KIND_UNKNOWN:
                log.info(f"  Skipping {key}")
                continue

            log.info(f"  Collecting {key}")
            filename = FIRMWARE_NAME_TEMPLATES[dev_kind] % (machine)

            if filename in collected:
                raise Exception(f"Tried to collect firmware {filename} twice!")

            data = plist_to_bin[dev_kind](val)
            fw = FWFile(filename, data)
            self.fwfiles.append((filename, fw))

            collected.add(filename)
            log.info(f"  Collected {key} as {filename}")

    def files(self):
        return self.fwfiles
