# SPDX-License-Identifier: GPL-2.0-or-later

import json, os, shutil, subprocess

from dataclasses import dataclass

from . import bugs, m1n1, osenum, osinstall, stub, system

from .asahi_firmware.core import FWPackage
from .diskutil import DiskUtil, MIN_INSTALL_FREE
from .exceptions import *
from .util import *

PART_ALIGN = psize("1MiB")

STUB_SIZE = align_down(psize("2.5GB"), PART_ALIGN)

MIN_MACOS_VERSION = "13.5"
MIN_MACOS_VERSION_EXPERT = "12.3"

EDU_128GB_LIMIT = 150 * 1024 * 1024 * 1024

VENDORFW_DIR = "vendorfw"
FIRMWARE_ARCHIVE = "all_firmware.tar.gz"

LARGE_OVERHEAD = 16_000_000_000

# This feature is confusing, disable it for now
ALLOW_INSTALL_INTO_CONTAINER = False

ACTION_REPAIR = "repair"
ACTION_INSTALL_FREE = "install_free"
ACTION_INSTALL_CONTAINER = "install_container"
ACTION_RESIZE = "resize"
ACTION_WIPE = "wipe"
ACTION_SELECT_DISK = "select_disk"
ACTION_UPGRADE = "upgrade"
ACTION_VENDORFW = "vendorfw"
ACTION_VOLBOOTABLE = "volbootable"

STEP2_DIRECT = "direct"
STEP2_RECOVERY = "recovery"
STEP2_MACOS = "macos"

BOOT_RECOVERY = "recovery"
BOOT_BOOTED = "booted"
BOOT_UNKNOWN = "unknown"

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

@dataclass
class InstallInfo:
    vgid: str
    efi_partuuid: str = None

@dataclass
class ResizeInfo:
    total: int
    free: int
    min_free: int
    min_size: int
    overhead: int

    @property
    def avail(self):
        return self.total - self.min_size

    @property
    def min_perc(self):
        return 100 * self.min_size / self.total

    @property
    def has_large_overhead(self):
        return self.overhead > LARGE_OVERHEAD

    @property
    def can_shrink(self):
        return self.avail >= 2 * PART_ALIGN

    def frees_enough_for_install(self, size):
        return self.total - size > MIN_INSTALL_FREE

class InstallerCore:
    def __init__(self, version, progress_cb=None, verbose=False):
        self.version = version
        self.user_progress_cb = progress_cb
        self.progress_cb = self.report_progress
        self.cancel_requested = False
        self.verbose = verbose
        self.stage = "preparing"  # preparing, resizing, installing, finalising
        self.sysinfo = None
        self.chip_min_ver = None
        self.device = None
        self.osinfo = None
        self.cur_os = None
        self.default_os = None
        self.data = json.load(open("installer_data.json"))
        self.credentials_validated = False
        self.admin_user = None
        self.admin_password = None
        self.expert = False
        self.ipsw = None
        self.part = None
        self.ins = None
        self.osins = None
        self.osi = None
        self.m1n1 = "boot/m1n1.bin"
        self.m1n1_ver = m1n1.get_version(self.m1n1)
        self.dutil = DiskUtil(self.verbose)
        self.sys_disk = None
        self.cur_disk = None
        self.is_edu_128gb = False
        self.reset_partition_lists()

    def collect_system_info(self):
        self.sysinfo = system.SystemInfo()

    def check_system(self):
        if bugs.is_bugged(self.sysinfo):
            raise BuggyMacOSError

        self.chip_min_ver = CHIP_MIN_VER.get(self.sysinfo.chip_id, None)
        self.device = DEVICES.get(self.sysinfo.device_class, None)
        if not self.chip_min_ver or not self.device or (self.device.expert_only and not self.expert):
            raise UnsupportedDeviceError

        if self.sysinfo.boot_mode == "macOS" and (
            (not self.sysinfo.login_user)
            or self.sysinfo.login_user == "unknown"):
            raise NoLoginUserError

        min_ver = MIN_MACOS_VERSION_EXPERT if self.expert else MIN_MACOS_VERSION
        if split_ver(self.sysinfo.macos_ver) < split_ver(min_ver):
            raise MacOSTooOldError(min_ver)

    def report_progress(self, fraction, rate):
        if self.cancel_requested and self.stage == "preparing":
            raise InstallCancelled
        if self.user_progress_cb:
            self.user_progress_cb(fraction, rate)

    def request_cancel(self):
        self.cancel_requested = True

    def reset_partition_lists(self):
        self.partitions_freespace = []
        self.partitions_empty_apfs = []
        self.partitions_resizable = []
        self.partitions_incomplete = []
        self.partitions_no_volboot = []
        self.partitions_upgradeable = []
        self.partitions_vendorfw = []

    def disk_info_init(self):
        self.dutil.get_info()

        if self.sys_disk is None:
            self.cur_disk = self.sys_disk = self.dutil.find_system_disk()

        if self.expert:
            self.external_disks = self.dutil.find_external_disks()
        else:
            self.external_disks = None

        self.partitions = self.dutil.get_partitions(self.cur_disk)

    @property
    def is_gpt(self):
        return self.dutil.disks[self.cur_disk]["Content"] == "GUID_partition_scheme"

    def collect_os_info(self):
        self.osinfo = osenum.OSEnum(self.sysinfo, self.dutil, self.cur_disk)
        self.osinfo.collect(self.partitions)
        self.is_edu_128gb = self.dutil.get_disk_size(self.sys_disk) < EDU_128GB_LIMIT

        self.parse_partitions()
        self.classify_oses()

    def os_boot_state(self, os):
        if self.sysinfo.boot_vgid == os.vgid and self.sysinfo.boot_uuid == os.rec_vgid:
            return BOOT_RECOVERY
        elif self.sysinfo.boot_uuid == os.vgid:
            return BOOT_BOOTED
        elif self.sysinfo.boot_vgid == os.vgid:
            return BOOT_UNKNOWN
        return None

    def classify_oses(self):
        if self.cur_disk == self.sys_disk:
            self.cur_os = None
        self.default_os = None

        for p in self.partitions:
            if p.desc is None or not p.os:
                continue
            for osi in p.os:
                if not osi.version:
                    continue
                state = self.os_boot_state(osi)
                if state == BOOT_RECOVERY:
                    if p.type == "APFS":
                        self.cur_os = osi
                elif state == BOOT_BOOTED:
                    self.cur_os = osi
                if self.sysinfo.default_boot == osi.vgid:
                    self.default_os = osi
                if osi.stub and osi.m1n1_ver:
                    self.partitions_vendorfw.append((p, osi))
                if osi.stub and not osi.sys_vol_bootable:
                    self.partitions_no_volboot.append((p, osi))
                if osi.stub and osi.m1n1_ver and osi.m1n1_ver != self.m1n1_ver:
                    self.partitions_upgradeable.append((p, osi))
                elif osi.stub and not (osi.bp and osi.bp.get("coih", None)):
                    self.partitions_incomplete.append((p, osi))

        if self.cur_os is None and self.sysinfo.boot_mode != "macOS":
            self.cur_os = self.default_os

    def available_oses(self):
        os_list = self.data["os_list"]
        if not self.expert:
            os_list = [i for i in os_list if not i.get("expert", False)]
        if self.cur_disk != self.sys_disk:
            os_list = [i for i in os_list if i.get("external_boot", False)]
        return os_list

    def available_ipsws(self, supported_fw=None):
        sys_iboot = split_ver(self.sysinfo.sys_firmware)
        sys_macos = split_ver(self.sysinfo.macos_ver)
        sys_sfr = split_ver(self.sysinfo.sfr_full_ver)
        chip_min = split_ver(CHIP_MIN_VER.get(self.sysinfo.chip_id, "0"))
        device_min = split_ver(self.device.min_ver)
        minver = [ipsw for ipsw in IPSW_VERSIONS
                 if split_ver(ipsw.version) >= max(chip_min, device_min)
                 and (supported_fw is None or ipsw.version in supported_fw)
                 and (ipsw.devices is None or self.sysinfo.device_class in ipsw.devices)]
        avail = [ipsw for ipsw in minver
                 if split_ver(ipsw.min_iboot) <= sys_iboot
                 and split_ver(ipsw.min_macos) <= sys_macos
                 and split_ver(ipsw.min_sfr) <= sys_sfr
                 and (not ipsw.expert_only or self.expert)]

        minver.sort(key=lambda ipsw: split_ver(ipsw.version))

        if not avail:
            raise FirmwareTooOldError(minver[0].version if minver else None)

        return avail

    def load_ipsw(self, ipsw):
        self.ipsw = ipsw
        logging.info(f"Chosen IPSW version: {ipsw.version}")
        self.ins = stub.StubInstaller(self.sysinfo, self.dutil, self.osinfo, self.progress_cb)
        self.ins.load_ipsw(ipsw)

    def load_os_package(self, template):
        self.osins = osinstall.OSInstaller(self.dutil, self.data, template, self.progress_cb)
        self.osins.load_package()

    def min_os_size(self):
        return STUB_SIZE + (self.osins.min_size if self.expert else self.osins.min_recommended_size)

    def os_partition_size(self, alloc_size):
        if alloc_size is None:
            return None
        return alloc_size - STUB_SIZE

    def do_install(self, total_size=None):
        self.stage = "installing"
        user_log.info(f"Installing stub macOS into {self.part.name} ({self.part.label})")

        self.ins.prepare_volume(self.part)
        self.ins.check_volume()
        self.ins.install_files(self.cur_os)

        self.osins.partition_disk(self.part.name, total_size)

        pkg = None
        if self.osins.needs_firmware:
            os.makedirs(VENDORFW_DIR, exist_ok=True)
            pkg = FWPackage(VENDORFW_DIR)
            self.ins.collect_firmware(pkg)
            pkg.close()
            self.osins.firmware_package = pkg

        self.osins.install(self.ins)

        for i in self.osins.idata_targets:
            self.ins.collect_installer_data(i)
            shutil.copy("installer.log", os.path.join(i, "installer.log"))

    def install_into_free(self, free_part, alloc_size=None):
        self.stage = "installing"
        user_log.info(f"Creating new stub macOS named {self.osins.name}")
        logging.info(f"Creating stub macOS: {self.osins.name}")
        self.part = self.dutil.addPartition(free_part.name, "apfs", self.osins.name, STUB_SIZE)

        self.do_install(self.os_partition_size(alloc_size))

    def install_into_disk(self, alloc_size=None):
        self.stage = "installing"
        user_log.info(f"Partitioning the whole disk ({self.cur_disk})")
        self.part = self.dutil.partitionDisk(self.cur_disk, "apfs", self.osins.name, STUB_SIZE)

        user_log.info(f"Creating new stub macOS named {self.osins.name}")
        logging.info(f"Creating stub macOS: {self.osins.name}")
        self.do_install(self.os_partition_size(alloc_size))

    def install_into_container(self, part):
        self.part = part

        self.do_install()

    def load_existing_install(self, part, osi):
        self.part = part
        self.ins = stub.StubInstaller(self.sysinfo, self.dutil, self.osinfo, self.progress_cb)
        if not self.ins.check_existing_install(osi):
            raise ExistingInstallError

    def get_m1n1_vars(self):
        # Note: we get the vars out of the boot.bin in the system volume instead of the
        # actual installed fuOS. This is arguably the better option, since it allows
        # users to fix their install using this functionality if they messed up the boot
        # object.
        vars = m1n1.extract_vars(self.ins.boot_obj_path)
        if vars is None:
            raise M1n1VarsError(self.ins.boot_obj_path)
        return vars

    def repair_install(self, part, osi, upgrade):
        self.load_existing_install(part, osi)

        self.dutil.remount_rw(self.ins.osi.system)
        self.ins.repair(self.cur_os)

        if upgrade:
            vars = self.get_m1n1_vars()

            user_log.info("Transferring m1n1 variables:")
            for v in vars:
                user_log.info(f"  {v}")

            m1n1.build(self.m1n1, self.ins.boot_obj_path, vars)

        # Unhide the SystemVersion, if hidden
        self.ins.prepare_for_bless()

    def set_vol_bootable(self, part, osi):
        self.part = part
        osi.set_volbootable(True)

    def rebuild_vendorfw(self, part, osi):
        self.load_existing_install(part, osi)

        vars = self.get_m1n1_vars()

        esp_id = None
        for var in vars:
            k, v = var.split('=')
            if k == "chosen.asahi,efi-system-partition":
                esp_id = v
                break
        if esp_id is None:
            raise EspNotFoundError

        target = self.dutil.get_partition_info(esp_id)
        mountpoint = self.dutil.mount(target.name)

        os.makedirs(VENDORFW_DIR, exist_ok=True)
        fw_pkg = FWPackage(VENDORFW_DIR)
        ipsw = None
        for ver in IPSW_VERSIONS:
            if ver.version == osi.version:
                ipsw = ver
                break
        if ipsw is None:
            raise UnsupportedVersionError(osi.version)

        self.ins.load_ipsw(ipsw)
        self.ins.load_identity()
        self.ins.collect_firmware(fw_pkg)
        fw_pkg.close()

        user_log.info(f"  Copying firmware into {target.name} partition...")
        base = os.path.join(mountpoint, "vendorfw")
        logging.info(f"Firmware -> {base}")
        shutil.copytree(fw_pkg.path, base, dirs_exist_ok=True)
        asahi = os.path.join(mountpoint, "asahi")
        shutil.copy(FIRMWARE_ARCHIVE, os.path.join(asahi, FIRMWARE_ARCHIVE))

    def get_resize_info(self, target):
        limits = self.dutil.get_resize_limits(target.name)

        total = target.container["CapacityCeiling"]
        free = target.container["CapacityFree"]
        min_free = target.min_free_space(self.expert or self.is_edu_128gb)
        # Minimum size, ignoring APFS snapshots & co, but with a conservative buffer
        min_size_raw = align_up(total - free + min_free, PART_ALIGN)
        # Minimum size reported by diskutil, considering APFS snapshots & co but with a less conservative buffer
        min_size_safe = limits["MinimumSizePreferred"]
        min_size = max(min_size_raw, min_size_safe)

        if free <= min_free:
            raise PartitionNoFreeSpaceError(f"{target.name} has no space to free")

        return ResizeInfo(total=total, free=free, min_free=min_free,
                          min_size=min_size, overhead=min_size - min_size_raw)

    def check_resize_size(self, info, size):
        size = align_up(size, PART_ALIGN)
        if size < info.min_size:
            raise SizeTooSmallError(info.min_size)
        if size >= info.total:
            raise SizeTooLargeError(info.total)
        return size

    def resize_partition(self, target, size):
        self.stage = "resizing"
        self.dutil.resizeContainer(target.name, size)

    def check_os_size(self, size, min_size, free_size):
        size = align_down(size, PART_ALIGN)
        if size < min_size:
            raise SizeTooSmallError(min_size)
        if size > free_size:
            raise SizeTooLargeError(free_size)
        return size

    def available_actions(self):
        actions = []

        if self.partitions_incomplete:
            actions.append(ACTION_REPAIR)
        if self.partitions_freespace and self.is_gpt:
            actions.append(ACTION_INSTALL_FREE)
        if ALLOW_INSTALL_INTO_CONTAINER and self.partitions_empty_apfs and self.is_gpt:
            actions.append(ACTION_INSTALL_CONTAINER)
        if self.partitions_resizable and self.is_gpt:
            actions.append(ACTION_RESIZE)
        if self.cur_disk != self.sys_disk:
            actions.append(ACTION_WIPE)
        if self.external_disks:
            actions.append(ACTION_SELECT_DISK)
        if self.partitions_upgradeable:
            actions.append(ACTION_UPGRADE)
        if self.partitions_vendorfw:
            actions.append(ACTION_VENDORFW)
        if self.partitions_no_volboot:
            actions.append(ACTION_VOLBOOTABLE)

        return actions

    def usable_free_areas(self, min_size):
        return [p for p in self.partitions_freespace
                if align_down(p.size, PART_ALIGN) >= min_size]

    def select_disk(self, disk=None):
        self.cur_disk = disk or self.sys_disk

    def admin_candidates(self):
        if self.sysinfo.boot_mode == "macOS":
            return [self.sysinfo.login_user]
        return self.cur_os.admin_users

    def set_admin_credentials(self, user, password):
        self.admin_user = user
        self.admin_password = password

    def set_reduced_security(self):
        self.stage = "finalising"
        subprocess.run(["bputil", "-g", "-v", self.ins.osi.vgid,
                        "-u", self.admin_user, "-p", self.admin_password], check=True)
        self.credentials_validated = True

    def bless(self, use_stdin=True):
        self.stage = "finalising"
        cmd = ["bless", "--setBoot",
               "--device", "/dev/" + self.ins.osi.sys_volume,
               "--user", self.admin_user]
        if use_stdin:
            subprocess.run(cmd + ["--stdinpass"],
                           input=self.admin_password.encode("utf-8"),
                           check=True)
        else:
            subprocess.run(cmd, check=True)
        self.credentials_validated = True

    def step2_mode(self):
        is_1tr = self.sysinfo.boot_mode == "one true recoveryOS"
        is_recovery = "recoveryOS" in self.sysinfo.boot_mode
        if is_1tr and self.ins.osi.paired:
            return STEP2_DIRECT
        elif is_recovery:
            return STEP2_RECOVERY
        return STEP2_MACOS

    def run_step2_script(self):
        self.stage = "finalising"
        subprocess.run([self.ins.step2_sh], check=True)

    def hide_new_volume(self):
        self.stage = "finalising"
        # Hide the new volume until step2 is done
        self.ins.prepare_for_step2()

    def get_install_info(self):
        info = InstallInfo(vgid=self.ins.osi.vgid)
        if self.osins and self.osins.efi_part:
            info.efi_partuuid = self.osins.efi_part.uuid.lower()
        return info

    def reboot(self):
        os.system("shutdown -r now")

    def shutdown(self):
        os.system("shutdown -h now")

    def parse_partitions(self):
        self.reset_partition_lists()
        for i, p in enumerate(self.partitions):
            p.index = i
            if p.type in ["Apple_APFS_ISC"]:
                continue
            if p.free:
                p.desc = f"(free space: {ssize(p.size)})"
                if p.size >= STUB_SIZE:
                    self.partitions_freespace.append(p)
            elif p.type.startswith("Apple_APFS"):
                p.desc = "APFS"
                if p.type == "Apple_APFS_Recovery":
                    p.desc += " (System Recovery)"
                if p.label is not None:
                    p.desc += f" [{p.label}]"
                if p.container is None:
                    p.desc += f" (not a container)"
                else:
                    volumes = p.container["Volumes"]
                    p.desc += f" ({ssize(p.size)}, {len(volumes)} volume{'s' if len(volumes) != 1 else ''})"
                    try:
                        if p.can_resize(self.expert or self.is_edu_128gb):
                            self.partitions_resizable.append(p)
                    except Exception as e:
                        logging.info(f"{e}")
                        if p.size >= STUB_SIZE * 0.95:
                            self.partitions_empty_apfs.append(p)
            else:
                p.desc = f"{p.type} ({ssize(p.size)})"

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

    def update_preboot(self):
        proc = subprocess.run(["diskutil", "apfs", "updatePreboot", self.cur_os.system], check = True,
                              stdout = subprocess.PIPE,
                              stderr = subprocess.STDOUT)
        logging.debug(f"Preboot update stdout: {proc.stdout}")

        self.cur_os.update_admin_users()
