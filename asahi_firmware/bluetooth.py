# SPDX-License-Identifier: MIT
import logging, os, os.path, re, sys
from collections import namedtuple, defaultdict

from .core import FWFile

BluetoothChip = namedtuple(
    "BluetoothChip", ("chip", "stepping", "board_type", "vendor")
)


class BluetoothFWCollection(object):
    VENDORMAP = {
        "MUR": "m",
        "USI": "u",
        "GEN": None,
    }

    def __init__(self, source_path):
        self.fwfiles = defaultdict(lambda: [None, None])
        self.load(source_path)

    def load(self, source_path):
        for fname in os.listdir(source_path):
            root, ext = os.path.splitext(fname)

            # index for bin and ptb inside self.fwfiles
            if ext == ".bin":
                idx = 0
            elif ext == ".ptb":
                idx = 1
            else:
                # skip firmware for older (UART) chips
                continue

            # skip T2 _DEV firmware
            if "_DEV" in root:
                continue

            chip = self.parse_fname(root)
            if chip is None:
                continue

            if self.fwfiles[chip][idx] is not None:
                logging.warning(f"duplicate entry for {chip}: {self.fwfiles[chip][idx].name} and now {fname + ext}")
                continue

            path = os.path.join(source_path, fname)
            with open(path, "rb") as f:
                data = f.read()

            self.fwfiles[chip][idx] = FWFile(fname, data)

    def parse_fname(self, fname):
        fname = fname.split("_")

        match = re.fullmatch("bcm(43[0-9]{2})([a-z][0-9])", fname[0].lower())
        if not match:
            logging.warning(f"Unexpected firmware file: {fname}")
            return None
        chip, stepping = match.groups()

        # board type is either preceeded by PCIE_macOS or by PCIE
        try:
            pcie_offset = fname.index("PCIE")
        except:
            logging.warning(f"Can't find board type in {fname}")
            return None

        if fname[pcie_offset + 1] == "macOS":
            board_type = fname[pcie_offset + 2]
        else:
            board_type = fname[pcie_offset + 1]
        board_type = "apple," + board_type.lower()

        # make sure we can identify exactly one vendor
        otp_values = set()
        for vendor, otp_value in self.VENDORMAP.items():
            if vendor in fname:
                otp_values.add(otp_value)
        if len(otp_values) != 1:
            logging.warning(f"Unable to determine vendor ({otp_values}) in {fname}")
            return None
        vendor = otp_values.pop()

        return BluetoothChip(
            chip=chip, stepping=stepping, board_type=board_type, vendor=vendor
        )

    def files(self):
        for chip, (bin, ptb) in self.fwfiles.items():
            fname_base = f"brcm/brcmbt{chip.chip}{chip.stepping}-{chip.board_type}"
            if chip.vendor is not None:
                fname_base += f"-{chip.vendor}"

            if bin is None:
                logging.warning(f"no bin for {chip}")
                continue
            else:
                yield fname_base + ".bin", bin

            if ptb is None:
                logging.warning(f"no ptb for {chip}")
                continue
            else:
                yield fname_base + ".ptb", ptb


if __name__ == "__main__":
    col = BluetoothFWCollection(sys.argv[1])

    if len(sys.argv) > 2:
        from . import FWPackage

        pkg = FWPackage(sys.argv[2])
        pkg.add_files(sorted(col.files()))
        pkg.close()

        for i in pkg.manifest:
            print(i)
    else:
        for name, fwfile in col.files():
            print(name, f"{fwfile.name} ({len(fwfile.data)} bytes)")
