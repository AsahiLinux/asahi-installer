# SPDX-License-Identifier: MIT
import base64, plistlib, struct, subprocess

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
        if boot_vgid is None:
            self.boot_vgid = self.boot_uuid
        else:
            self.boot_vgid = self.get_str(boot_vgid)
        self.product_name = self.get_str(product["product-name"])
        self.soc_name = self.get_str(product["product-soc-name"])

        self.get_nvram_data()

        bputil_info = b''
        for vgid in (self.boot_vgid, self.default_boot):
            try:
                bputil_info = subprocess.run(["bputil", "-d", "-v",
                                              vgid],
                                             check=True,
                                             capture_output=True).stdout
                break
            except subprocess.CalledProcessError:
                continue

        self.boot_mode = "Unknown"
        # one of 'macOS', 'one true recoveryOS', 'recoveryOS'
        if b"Current OS environment: " in bputil_info:
            self.boot_mode = (bputil_info.split(b"Current OS environment: ")[1]
                              .split(b"\n")[0].decode("ascii"))
        elif b"OS Type" in bputil_info:
            boot_mode = bputil_info.split(b"OS Type")[1].split(b"\n")[0]
            self.boot_mode = boot_mode.split(b": ")[1].decode("ascii")

        self.macos_ver, self.macos_build = self.get_version("/System/Library/CoreServices/SystemVersion.plist")
        self.sfr_ver, self.sfr_build = self.get_version("/System/Volumes/iSCPreboot/SFR/current/SystemVersion.plist")

        self.login_user = None
        consoleuser = subprocess.run(["scutil"],
                                     input=b"show State:/Users/ConsoleUser\n",
                                     stdout=subprocess.PIPE).stdout.strip()
        if b"kCGSSessionUserNameKey : " in consoleuser:
            self.login_user = (consoleuser.split(b"kCGSSessionUserNameKey : ")[1]
                               .split(b"\n")[0].decode("ascii"))

    def get_nvram_data(self):
        nvram_data = subprocess.run(["nvram", "-p"],
                                    stdout=subprocess.PIPE, check=True).stdout
        
        self.nvram = {}
        
        for line in nvram_data.rstrip(b"\n").split(b"\n"):
            line = line.decode("ascii")
            k, v = line.split("\t", 1)
            self.nvram[k] = v

        self.default_boot = None
        if "boot-volume" in self.nvram:
            self.default_boot = self.nvram["boot-volume"].split(":")[2]

    def get_version(self, name):
        data = plistlib.load(open(name, "rb"))
        return data["ProductVersion"], data["ProductBuildVersion"]

    def show(self):
        print(f"System information:")
        print(f"  Product name: {self.product_name}")
        print(f"  SoC: {self.soc_name}")
        print(f"  Device class: {self.device_class}")
        print(f"  Product type: {self.product_type}")
        print(f"  Board ID: {self.board_id:#x}")
        print(f"  Chip ID: {self.chip_id:#x}")
        print(f"  System firmware: {self.sys_firmware}")
        print(f"  Boot UUID: {self.boot_uuid}")
        print(f"  Boot VGID: {self.boot_vgid}")
        print(f"  Default boot VGID: {self.default_boot}")
        print(f"  Boot mode: {self.boot_mode}")
        print(f"  OS version: {self.macos_ver} ({self.macos_build})")
        print(f"  SFR version: {self.sfr_ver} ({self.sfr_build})")
        print(f"  Login user: {self.login_user}")

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
        
