# SPDX-License-Identifier: MIT
import os, plistlib, subprocess, logging
from .core import FWFile

log = logging.getLogger("asahi_firmware.als")
FACTORY_DIR = "/System/Volumes/Hardware/FactoryData/System/Library/Caches/com.apple.factorydata"
FILENAME = "apple/aop-als-cal.bin"

class AlsFWCollection(object):
    def __init__(self, path=None):
        self.fwfiles = []
        if path is None:
            self.load()
        else:
            self.update(path)
    def files(self):
        return self.fwfiles
    def copy_raw(self, path):
        try:
            for f in os.listdir(path):
                if not f.startswith('HmCA'):
                    continue
                data = open(f'{path}/{f}', 'rb').read()
                name = f'apple/{f}'
                fw = FWFile(name, data)
                self.fwfiles.append((name, fw))
        except:
            log.warning("Unable to find raw ambient light sensor calibration data")
            return
    def update(self, path):
        try:
            data = open(f'{path}/{FILENAME}', 'rb').read()
            fw = FWFile(FILENAME, data)
            self.fwfiles.append((FILENAME, fw))
        except:
            log.warning("Unable to find ambient light sensor calibration data")
            return
        self.copy_raw(f'{path}/com.apple.factorydata')
    def load(self):
        ioreg = subprocess.run(["ioreg", "-r", "-a", "-n", "als", "-l"], capture_output=True)
        if ioreg.returncode != 0:
            log.warning("Unable to run ioreg, ambient light sensor calibration will not be saved")
            return
        if len(ioreg.stdout) == 0:
            log.info("ioreg without 'als' object. Possibly a device without ambient light sensor.")
            return
        tree = plistlib.loads(ioreg.stdout)
        try:
            cal_data = tree[0]["IORegistryEntryChildren"][0]["IORegistryEntryChildren"][0]["IORegistryEntryChildren"][0]["CalibrationData"]
        except:
            log.warning("Unable to find ambient light sensor calibration data")
            return
        fw = FWFile(FILENAME, cal_data)
        self.fwfiles.append((FILENAME, fw))
        log.info(f"  Collected {FILENAME}")
        self.copy_raw(FACTORY_DIR)
