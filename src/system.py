# SPDX-License-Identifier: MIT
import base64, plistlib, struct, subprocess, logging

from util import *

class SystemInfo:
    def __init__(self):
        self.fetch()

    def fetch(self):
        result = subprocess.run(["ioreg", "-alp", "IODeviceTree"],
                                stdout=subprocess.PIPE, check=True)

        self.ioreg = plistlib.loads(result.stdout)

        for dt in self.ioreg["IORegistryEntryChildren"]:
            if dt.get("IOObjectClass", None) == "IOPlatformExpertDevice":
                break
        else:
            raise Exception("Could not find IOPlatformExpertDevice")

        self.dt = dt
        self.chosen = chosen = self.get_child(dt, "chosen")
        self.product = product = self.get_child(dt, "product")

        sys_compat = self.get_list(dt["compatible"])
        self.device_class = sys_compat[0].lower()
        self.product_type = sys_compat[1]
        self.board_id = self.get_int(chosen["board-id"])
        self.chip_id = self.get_int(chosen["chip-id"])
        self.sys_firmware = self.get_str(chosen["system-firmware-version"])
        self.boot_uuid = self.get_str(chosen["boot-uuid"])
        boot_vgid = chosen.get("associated-volume-group", None)
        if boot_vgid is None:
            boot_vgid = chosen.get("apfs-preboot-uuid", None)
        if boot_vgid is not None:
            self.boot_vgid = self.get_str(boot_vgid)
        else:
            boot_path = chosen.get("boot-objects-path", None)
            if boot_path:
                self.boot_vgid = self.get_str(boot_path).split("/")[1]
            else:
                self.boot_vgid = self.boot_uuid
        self.product_name = self.get_str(product["product-name"])
        self.soc_name = self.get_str(product["product-soc-name"])

        self.get_nvram_data()

        bputil_info = b''
        for vgid in (self.boot_vgid, self.default_boot):
            if not vgid:
                continue
            try:
                bputil_info = subprocess.run(["bputil", "-d", "-v",
                                              vgid],
                                             check=True,
                                             capture_output=True).stdout
                break
            except subprocess.CalledProcessError:
                continue

        self.boot_mode = "Unknown"
        # one of 'macOS', 'one true recoveryOS', 'recoveryOS'(?), 'ordinary recoveryOS'
        if b"Current OS environment: " in bputil_info:
            self.boot_mode = (bputil_info.split(b"Current OS environment: ")[1]
                              .split(b"\n")[0].decode("ascii"))
        elif b"OS Type" in bputil_info:
            boot_mode = bputil_info.split(b"OS Type")[1].split(b"\n")[0]
            self.boot_mode = boot_mode.split(b": ")[1].decode("ascii")

        self.macos_ver, self.macos_build = self.get_version("/System/Library/CoreServices/SystemVersion.plist")
        self.sfr_ver, self.sfr_build = self.get_version("/System/Volumes/iSCPreboot/SFR/current/SystemVersion.plist")
        self.fsfr_ver, self.fsfr_build = self.get_version("/System/Volumes/iSCPreboot/SFR/fallback/SystemVersion.plist")
        self.sfr_full_ver = self.get_restore_version("/System/Volumes/iSCPreboot/SFR/current/RestoreVersion.plist")

        self.login_user = None
        scout = subprocess.run(["scutil"], input=b"show State:/Users/ConsoleUser\n",
                               stdout=subprocess.PIPE).stdout.strip()
        for line in scout.split(b"\n"):
            if b"kCGSSessionUserNameKey : " in line:
                consoleuser = line.split(b"kCGSSessionUserNameKey : ")[1].decode("ascii")
                if consoleuser != "_mbsetupuser":
                    self.login_user = consoleuser

    def get_nvram_data(self):
        nvram_data = subprocess.run(["nvram", "-p"],
                                    stdout=subprocess.PIPE, check=True).stdout

        self.nvram = {}

        for line in nvram_data.rstrip(b"\n").split(b"\n"):
            try:
                k, v = line.split(b"\t", 1)
                k = k.decode("ascii")
                v = v.decode("utf-8")
                self.nvram[k] = v
            except:
                logging.warning(f"Bad nvram line: {line!r}")
                continue # Hopefully we don't need this value...

        self.default_boot = None
        if "boot-volume" in self.nvram:
            self.default_boot = self.nvram["boot-volume"].split(":")[2]

    def get_version(self, name):
        try:
            data = plistlib.load(open(name, "rb"))
            return data["ProductVersion"], data["ProductBuildVersion"]
        except:
            return None, None

    def get_restore_version(self, name):
        try:
            data = plistlib.load(open(name, "rb"))
            return data["RestoreLongVersion"]
        except:
            return None

    def show(self):
        p_info(f"  Product name: {col()}{self.product_name}")
        p_info(f"  SoC: {col()}{self.soc_name}")
        p_info(f"  Device class: {col()}{self.device_class}")
        p_info(f"  Product type: {col()}{self.product_type}")
        p_info(f"  Board ID: {col()}{self.board_id:#x}")
        p_info(f"  Chip ID: {col()}{self.chip_id:#x}")
        p_info(f"  System firmware: {col()}{self.sys_firmware}")
        p_info(f"  Boot UUID: {col()}{self.boot_uuid}")
        p_info(f"  Boot VGID: {col()}{self.boot_vgid}")
        p_info(f"  Default boot VGID: {col()}{self.default_boot}")
        p_info(f"  Boot mode: {col()}{self.boot_mode}")
        p_info(f"  OS version: {col()}{self.macos_ver} ({self.macos_build})")
        p_info(f"  SFR version: {col()}{self.sfr_full_ver}")
        p_info(f"  System rOS version: {col()}{self.sfr_ver} ({self.sfr_build})")
        if self.fsfr_ver:
            p_info(f"  Fallback rOS version: {col()}{self.fsfr_ver} ({self.fsfr_build})")
        else:
            p_info(f"  No Fallback rOS")
        p_info(f"  Login user: {col()}{self.login_user}")

    def get_child(self, obj, name):
        for child in obj["IORegistryEntryChildren"]:
            if child.get("IORegistryEntryName", None) == name:
                break
        else:
            raise Exception(f"Could not find {name}")

        return child

    def get_list(self, val):
        return [i.decode("ascii") for i in val.rstrip(b"\x00").split(b"\x00")]

    def get_str(self, val):
        return val.rstrip(b"\0").decode("ascii")

    def get_int(self, val):
        return struct.unpack("<I", val)[0]

