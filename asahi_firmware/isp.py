# SPDX-License-Identifier: MIT
import struct, os, logging
from collections import namedtuple
from .core import FWFile

SetFile = namedtuple('SetFile', ['sensor', 'magic', 'name', 'size'])

ISP_PREFIX = "apple/isp_"
ISP_SETFILE_ALIGNMENT = 0x1000
ISP_SETFILES = [
    SetFile(0x248, 0x18200103, "1820_01XX", 0x442c),
    SetFile(0x248, 0x18220201, "1822_02XX", 0x442c),
    # SetFile(0x343, 0x52210211, "5221_02XX", 0x4870),
    # SetFile(0x354, 0x92510208, "9251_02XX", 0xa5ec),
    # SetFile(0x356, 0x48200107, "4820_01XX", 0x9324),
    # SetFile(0x356, 0x48200206, "4820_02XX", 0x9324),
    SetFile(0x364, 0x87200103, "8720_01XX", 0x36ac),
    SetFile(0x364, 0x87230101, "8723_01XX", 0x361c),
    # SetFile(0x372, 0x38200108, "3820_01XX", 0xfdb0),
    # SetFile(0x372, 0x38200205, "3820_02XX", 0xfdb0),
    # SetFile(0x372, 0x38201104, "3820_11XX", 0xfdb0),
    # SetFile(0x372, 0x38201204, "3820_12XX", 0xfdb0),
    # SetFile(0x405, 0x97200102, "9720_01XX", 0x92c8),
    # SetFile(0x405, 0x97210102, "9721_01XX", 0x9818),
    # SetFile(0x405, 0x97230101, "9723_01XX", 0x92c8),
    # SetFile(0x414, 0x25200102, "2520_01XX", 0xa444),
    # SetFile(0x503, 0x78200109, "7820_01XX", 0xb268),
    # SetFile(0x503, 0x78200206, "7820_02XX", 0xb268),
    # SetFile(0x505, 0x39210102, "3921_01XX", 0x89b0),
    # SetFile(0x514, 0x28200108, "2820_01XX", 0xa198),
    # SetFile(0x514, 0x28200205, "2820_02XX", 0xa198),
    # SetFile(0x514, 0x28200305, "2820_03XX", 0xa198),
    # SetFile(0x514, 0x28200405, "2820_04XX", 0xa198),
    SetFile(0x558, 0x19210106, "1921_01XX", 0xad40),
    SetFile(0x558, 0x19220201, "1922_02XX", 0xad40),
    # SetFile(0x603, 0x79200109, "7920_01XX", 0xad2c),
    # SetFile(0x603, 0x79200205, "7920_02XX", 0xad2c),
    # SetFile(0x603, 0x79210104, "7921_01XX", 0xad90),
    # SetFile(0x613, 0x49200108, "4920_01XX", 0x9324),
    # SetFile(0x613, 0x49200204, "4920_02XX", 0x9324),
    # SetFile(0x614, 0x29210107, "2921_01XX", 0xed6c),
    # SetFile(0x614, 0x29210202, "2921_02XX", 0xed6c),
    # SetFile(0x614, 0x29220201, "2922_02XX", 0xed6c),
    # SetFile(0x633, 0x36220111, "3622_01XX", 0x100d4),
    # SetFile(0x703, 0x77210106, "7721_01XX", 0x936c),
    # SetFile(0x703, 0x77220106, "7722_01XX", 0xac20),
    # SetFile(0x713, 0x47210107, "4721_01XX", 0x936c),
    # SetFile(0x713, 0x47220109, "4722_01XX", 0x9218),
    # SetFile(0x714, 0x20220107, "2022_01XX", 0xa198),
    # SetFile(0x772, 0x37210106, "3721_01XX", 0xfdf8),
    # SetFile(0x772, 0x37211106, "3721_11XX", 0xfe14),
    # SetFile(0x772, 0x37220104, "3722_01XX", 0xfca4),
    # SetFile(0x772, 0x37230106, "3723_01XX", 0xfca4),
    # SetFile(0x814, 0x21230101, "2123_01XX", 0xed54),
    # SetFile(0x853, 0x76220112, "7622_01XX", 0x247f8),
    # SetFile(0x913, 0x75230107, "7523_01XX", 0x247f8),
    # SetFile(0xd56, 0x62210102, "6221_01XX", 0x1b80),
    # SetFile(0xd56, 0x62220102, "6222_01XX", 0x1b80),
]
ISP_SETFILE_MAP = {s.magic: s for s in ISP_SETFILES}
ISP_SETFILE_COUNT = len(ISP_SETFILES)
assert len(ISP_SETFILE_MAP) == ISP_SETFILE_COUNT

log = logging.getLogger("asahi_firmware.isp")

def round_up(x, y):
    return ((x + (y - 1)) & (-y))

def isp_setfile_header_check(hdr):
    return (
        (hdr[2] == 0x0) and
        (hdr[3] == 0x0) and
        (hdr[4] & 0xff000000 == hdr[4]) and (hdr[4]) and
        (hdr[5] & 0xffff0000 == hdr[5]) and (hdr[5]) and
        (hdr[6] == 0x0) and
        (hdr[7] == 0x3c00000)
    )

class ISPFWCollection(object):
    def __init__(self, source_path):
        self.fwfiles = []
        self.load(source_path)

    def extract_isp(self, data):
        files = []
        found = 0
        for offset in range(0, len(data), ISP_SETFILE_ALIGNMENT):
            hdrdata = data[offset:offset + 8*4]
            if len(hdrdata) < 8*4:
                break

            # search for valid header and magic constant at 4K boundary
            header = struct.unpack(">8L", hdrdata)
            if not isp_setfile_header_check(header): continue
            setfile = ISP_SETFILE_MAP.get(header[0], None)
            if not setfile:
                continue

            size = round_up(setfile.size, 64)  # align to be safe
            dat = data[offset:offset + size]
            sensor_name = f"{setfile.sensor:x}_{setfile.name}"

            log.info(f"isp-extract: {found + 1}/{ISP_SETFILE_COUNT}: Found sensor {sensor_name} data at offset {offset:#x}")
            yield FWFile(f"apple/isp_{setfile.name}.dat", dat)

            found += 1

        if found != ISP_SETFILE_COUNT:
            log.warn(f"isp-extract: Found {found}/{ISP_SETFILE_COUNT} calibration files.")
        else:
            log.info(f"isp-extract: Found all {found}/{ISP_SETFILE_COUNT} sensor calibration files!")

    def load(self, source_path):
        if os.path.isdir(source_path):
            bin_path = os.path.join(source_path, "appleh13camerad")
        else:
            bin_path = source_path

        if not os.path.exists(bin_path):
            log.warn("appleh13camerad not found, cannot extract ISP camera calibration firmwares. Webcam output will be low quality.")
            return

        log.info(f"Extracting firmware from camera daemon at {bin_path}")

        with open(bin_path, "rb") as fd:
            data = fd.read()

        for fwf in self.extract_isp(data):
            self.fwfiles.append((fwf.name, fwf))

    def files(self):
        return self.fwfiles

