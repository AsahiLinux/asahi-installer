# SPDX-License-Identifier: GPL-2.0-or-later

import json
from dataclasses import dataclass

from . import m1n1

from .exceptions import *
from .util import *

PART_ALIGN = psize("1MiB")

STUB_SIZE = align_down(psize("2.5GB"), PART_ALIGN)

# Minimum free space to leave when resizing, to allow for OS upgrades
MIN_FREE_OS = psize("38GB")
# Minimum free space to leave for non-OS containers
MIN_FREE = psize("1GB")

# 2.5GB stub + 5GB OS + 0.5GB EFI = 8GB, round up to 10GB
MIN_INSTALL_FREE = psize("10GB")

MIN_MACOS_VERSION = "13.5"
MIN_MACOS_VERSION_EXPERT = "12.3"

@dataclass
class IPSW:
    version: str
    min_macos: str
    min_iboot: str
    min_sfr: str
    expert_only: bool
    devices: list
    url: str

@dataclass
class Device:
    min_ver: str
    expert_only: bool

CHIP_MIN_VER = {
    0x8103: "11.0",     # T8103, M1
    0x6000: "12.0",     # T6000, M1 Pro
    0x6001: "12.0",     # T6001, M1 Max
    0x6002: "12.3",     # T6002, M1 Ultra
    0x8112: "12.4",     # T8112, M2
    0x6020: "13.1",     # T6020, M2 Pro
    0x6021: "13.1",     # T6021, M2 Max
    0x6022: "13.4",     # T6022, M2 Ultra
    0x8122: "14.8.3",   # T8122, M3
    0x6030: "14.8.3",   # T6030, M3 Pro
    0x6031: "14.8.3",   # T6031, M3 Max (16-core)
    0x6034: "14.8.3",   # T6034, M3 Max (14-core)
}

DEVICES = {
    "j274ap":   Device("11.0", False),  # Mac mini (M1, 2020)
    "j293ap":   Device("11.0", False),  # MacBook Pro (13-inch, M1, 2020)
    "j313ap":   Device("11.0", False),  # MacBook Air (M1, 2020)
    "j456ap":   Device("11.3", False),  # iMac (24-inch, M1, 2021)
    "j457ap":   Device("11.3", False),  # iMac (24-inch, M1, 2021)
    "j314cap":  Device("12.0", False),  # MacBook Pro (14-inch, M1 Max, 2021)
    "j314sap":  Device("12.0", False),  # MacBook Pro (14-inch, M1 Pro, 2021)
    "j316cap":  Device("12.0", False),  # MacBook Pro (16-inch, M1 Max, 2021)
    "j316sap":  Device("12.0", False),  # MacBook Pro (16-inch, M1 Pro, 2021)
    "j375cap":  Device("12.3", False),  # Mac Studio (M1 Max, 2022)
    "j375dap":  Device("12.3", False),  # Mac Studio (M1 Ultra, 2022)
    "j413ap":   Device("12.4", False),  # MacBook Air (M2, 2022)
    "j493ap":   Device("12.4", False),  # MacBook Pro (13-inch, M2, 2022)
    "j414cap":  Device("13.2", False),  # MacBook Pro (14-inch, M2 Max, 2023)
    "j414sap":  Device("13.2", False),  # MacBook Pro (14-inch, M2 Pro, 2023)
    "j416cap":  Device("13.2", False),  # MacBook Pro (16-inch, M2 Max, 2023)
    "j416sap":  Device("13.2", False),  # MacBook Pro (16-inch, M2 Pro, 2023)
    "j473ap":   Device("13.2", False),  # Mac mini (M2, 2023)
    "j474sap":  Device("13.2", False),  # Mac mini (M2 Pro, 2023)
    "j415ap":   Device("13.4", False),  # MacBook Air (15-inch, M2, 2023)
    "j475cap":  Device("13.4", False),  # Mac Studio (M2 Max, 2023)
    "j475dap":  Device("13.4", False),  # Mac Studio (M2 Ultra, 2023)
    "j180dap":  Device("13.4", False),  # Mac Pro (M2 Ultra, 2023)
    "j433ap":   Device("14.8.3", False), # iMac (24-inch, M3, 2023)
    "j434ap":   Device("14.8.3", False), # iMac (24-inch, M3, 2023)
    "j504ap":   Device("14.8.3", False), # MacBook Pro (14-inch, M3, 2023)
    "j613ap":   Device("14.8.3", False), # MacBook Air (13-inch, M3, 2024)
    "j615ap":   Device("14.8.3", False), # MacBook Air (15-inch, M3, 2024)
    "j514sap":  Device("14.8.3", False), # MacBook Pro (14-inch, M3 Pro, 2023)
    "j514cap":  Device("14.8.3", False), # MacBook Pro (14-inch, M3 Max, 2023)
    "j514map":  Device("14.8.3", False), # MacBook Pro (14-inch, M3 Max, 2023)
    "j516sap":  Device("14.8.3", False), # MacBook Pro (16-inch, M3 Pro, 2023)
    "j516cap":  Device("14.8.3", False), # MacBook Pro (16-inch, M3 Max, 2023)
    "j516map":  Device("14.8.3", False), # MacBook Pro (16-inch, M3 Max, 2023)
}

# Asahi Linux does not support running in a virtual machine, this option
# exists only for development of the installer itself.
if os.environ.get("ALLOW_VM", None):
    CHIP_MIN_VER[0xfe00] = "12.0"
    DEVICES["vma2macosap"] = Device("12.0", False)

IPSW_VERSIONS = [
    IPSW("12.3.1",
         "12.1",
         "iBoot-7459.101.3",
         "21.5.258.0.0,0",
         False,
         None,
         "https://updates.cdn-apple.com/2022SpringFCS/fullrestores/002-79219/851BEDF0-19DB-4040-B765-0F4089D1530D/UniversalMac_12.3.1_21E258_Restore.ipsw"),
    IPSW("12.3",
         "12.1",
         "iBoot-7459.101.2",
         "21.5.230.0.0,0",
         False,
         None,
         "https://updates.cdn-apple.com/2022SpringFCS/fullrestores/071-08757/74A4F2A1-C747-43F9-A22A-C0AD5FB4ECB6/UniversalMac_12.3_21E230_Restore.ipsw"),
    IPSW("13.5",
         "13.0",
         "iBoot-8422.141.2",
         "22.7.74.0.0,0",
         False,
         None,
         "https://updates.cdn-apple.com/2023SummerFCS/fullrestores/032-69606/D3E05CDF-E105-434C-A4A1-4E3DC7668DD0/UniversalMac_13.5_22G74_Restore.ipsw"),
    IPSW("14.8.3",
         "14.6",
         "iBoot-10151.140.19",
         "23.10.220.0.0,0",
         False,
         ["j433ap", "j434ap", "j504ap", "j613ap", "j615ap", "j514sap", "j514cap", "j514map", "j516sap", "j516cap", "j516map"],
         "https://updates.cdn-apple.com/2025FallFCS/patches/089-71124/49AD260A-D47F-4B5E-A793-30446187196E/com_apple_MobileAsset_MacSoftwareUpdate/f6d1ac9149f6a06401ff87fae5b262c420bfc5f7.zip"),
]

class InstallerCore:
    def __init__(self, version):
        self.version = version
        self.data = json.load(open("installer_data.json"))
        self.credentials_validated = False
        self.expert = False
        self.ipsw = None
        self.osins = None
        self.osi = None
        self.m1n1 = "boot/m1n1.bin"
        self.m1n1_ver = m1n1.get_version(self.m1n1)
        self.sys_disk = None
        self.cur_disk = None

    def os_valid(self) -> bool:
        if self.cur_os is None:
            raise OSInvalidError

        return True

    def user_valid(self) -> bool:
        if not self.cur_os.admin_users or self.cur_os.admin_users == ["_mbsetupuser"]:
            raise NoAdminUsersError

        if self.sysinfo.boot_mode == "macOS" and self.sysinfo.login_user not in self.cur_os.admin_users:
            raise UserNotAdminError

        return True
