# SPDX-License-Identifier: MIT
import os, plistlib, subprocess, logging
from .core import FWFile

log = logging.getLogger("asahi_firmware.als")
FACTORY_DIR = "/System/Volumes/Hardware/FactoryData/System/Library/Caches/com.apple.factorydata/"

class AlsFWCollection(object):
    def __init__(self):
        self.fwfiles = []
        self.load()
    def files(self):
        return self.fwfiles
    def load(self):
        ioreg = subprocess.run(["ioreg", "-r", "-a", "-n", "als", "-l"], capture_output=True)
        if ioreg.returncode != 0:
            log.warning("Unable to run ioreg, ambient light sensor calibration will not be saved")
            return
        tree = plistlib.loads(ioreg.stdout)
        try:
            cal_data = tree[0]["IORegistryEntryChildren"][0]["IORegistryEntryChildren"][0]["IORegistryEntryChildren"][0]["CalibrationData"]
        except:
            log.warning("Unable to find ambient light sensor calibration data")
            return
        filename = "apple/aop-als-cal.bin"
        fw = FWFile(filename, cal_data)
        self.fwfiles.append((filename, fw))
        log.info(f"  Collected {filename}")
        try:
            for f in os.listdir(FACTORY_DIR):
                if not f.startswith('HmCA'):
                    continue
                data = open(f'{FACTORY_DIR}/{f}', 'rb').read()
                name = f'apple/{f}'
                fw = FWFile(name, data)
                self.fwfiles.append((name, fw))
        except:
            log.warning("Unable to find raw ambient light sensor calibration data")
            return
