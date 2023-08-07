#!/usr/bin/python3
# SPDX-License-Identifier: MIT
import os, os.path, shlex, subprocess, sys, time, termios, json, getpass, reporting
from dataclasses import dataclass

import system, osenum, stub, diskutil, osinstall, asahi_firmware, m1n1
from util import *

PART_ALIGN = psize("1MiB")

STUB_SIZE = align_down(psize("2.5GB"), PART_ALIGN)

# Minimum free space to leave when resizing, to allow for OS upgrades
MIN_FREE_OS = psize("38GB")
# Minimum free space to leave for non-OS containers
MIN_FREE = psize("1GB")

# 2.5GB stub + 5GB OS + 0.5GB EFI = 8GB, round up to 10GB
MIN_INSTALL_FREE = psize("10GB")

MIN_MACOS_VERSION = "12.3"
MIN_MACOS_VERSION_EXPERT = "12.3"

@dataclass
class IPSW:
    version: str
    min_macos: str
    min_iboot: str
    min_sfr: str
    expert_only: bool
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
    "j414cap":  Device("13.2", True),  # MacBook Pro (14-inch, M2 Max, 2023)
    "j414sap":  Device("13.2", True),  # MacBook Pro (14-inch, M2 Pro, 2023)
    "j416cap":  Device("13.2", True),  # MacBook Pro (16-inch, M2 Max, 2023)
    "j416sap":  Device("13.2", True),  # MacBook Pro (16-inch, M2 Pro, 2023)
    "j473ap":   Device("13.2", True),  # Mac mini (M2, 2023)
    "j474sap":  Device("13.2", True),  # Mac mini (M2 Pro, 2023)
    "j415ap":   Device("13.4", True),  # MacBook Air (15-inch, M2, 2023)
    "j475cap":  Device("13.4", True),  # Mac Studio (M2 Max, 2023)
    "j475dap":  Device("13.4", True),  # Mac Studio (M2 Ultra, 2023)
    "j180dap":  Device("13.4", True),  # Mac Pro (M2 Ultra, 2023)
}

IPSW_VERSIONS = [
    # This is the special M2 version, it comes ahead so it isn't the default in expert mode
    IPSW("12.4",
         "12.1",
         "iBoot-7459.121.3",
         "21.6.81.2.0,0",
         False,
         "https://updates.cdn-apple.com/2022SpringFCS/fullrestores/012-17781/F045A95A-44B4-4BA9-8A8A-919ECCA2BB31/UniversalMac_12.4_21F2081_Restore.ipsw"),
    IPSW("12.3.1",
         "12.1",
         "iBoot-7459.101.3",
         "21.5.258.0.0,0",
         False,
         "https://updates.cdn-apple.com/2022SpringFCS/fullrestores/002-79219/851BEDF0-19DB-4040-B765-0F4089D1530D/UniversalMac_12.3.1_21E258_Restore.ipsw"),
    IPSW("12.3",
         "12.1",
         "iBoot-7459.101.2",
         "21.5.230.0.0,0",
         False,
         "https://updates.cdn-apple.com/2022SpringFCS/fullrestores/071-08757/74A4F2A1-C747-43F9-A22A-C0AD5FB4ECB6/UniversalMac_12.3_21E230_Restore.ipsw"),
    IPSW("13.5",
         "13.0",
         "iBoot-8422.141.2",
         "22.7.74.0.0,0",
         False,
         "https://updates.cdn-apple.com/2023SummerFCS/fullrestores/032-69606/D3E05CDF-E105-434C-A4A1-4E3DC7668DD0/UniversalMac_13.5_22G74_Restore.ipsw"),
]

class InstallerMain:
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

    def input(self):
        self.flush_input()
        return input()

    def get_size(self, prompt, default=None, min=None, max=None, total=None):
        self.flush_input()
        if default is not None:
            prompt += f" ({default})"
        new_size = input_prompt(prompt + f": ").strip()
        try:
            if default is not None and not new_size:
                new_size = default
            if new_size.lower() == "min" and min is not None:
                val = min
            elif new_size.lower() == "max" and max is not None:
                val = max
            elif new_size.endswith("%") and total is not None:
                val = int(float(new_size[:-1]) * total / 100)
            elif new_size.endswith("B"):
                val = psize(new_size.upper())
            else:
                val = psize(new_size.upper() + "B")
        except Exception as e:
            print(e)
            val = None

        if val is None:
            p_error(f"Invalid size '{new_size}'.")

        return val

    def choice(self, prompt, options, default=None):
        is_array = False

        if isinstance(options, list):
            is_array = True
            options = {str(i+1): v for i, v in enumerate(options)}
            if default is not None:
                default += 1

        int_keys = all(isinstance(i, int) for i in options.keys())

        for k, v in options.items():
            p_choice(f"  {col(BRIGHT)}{k}{col(NORMAL)}: {v}")

        if default:
            prompt += f" ({default})"

        while True:
            self.flush_input()
            res = input_prompt(prompt + ": ").strip()
            if res == "" and default is not None:
                res = str(default)
            if res not in options:
                p_warning(f"Enter one of the following: {', '.join(map(str, options.keys()))}")
                continue
            print()
            if is_array:
                return int(res) - 1
            else:
                return res

    def yesno(self, prompt, default=False):
        if default:
            prompt += " (Y/n): "
        else:
            prompt += " (y/N): "

        while True:
            self.flush_input()
            res = input_prompt(prompt).strip()
            if not res:
                return default
            elif res.lower() in ("y", "yes", "1", "true"):
                return True
            elif res.lower() in ("n", "no", "0", "false"):
                return False

            p_warning(f"Please enter 'Y' or 'N'")

    def check_cur_os(self):
        if self.cur_os is None:
            p_error("Unable to determine primary OS.")
            p_error("This installer requires you to already have a macOS install with")
            p_error("at least one administrator user that is a machine owner.")
            p_error("Please run this installer from your main macOS instance or its")
            p_error("paired recovery, or ensure the default boot volume is set correctly.")
            sys.exit(1)

        p_progress(f"Using OS '{self.cur_os.label}' ({self.cur_os.sys_volume}) for machine authentication.")
        logging.info(f"Current OS: {self.cur_os.label} / {self.cur_os.sys_volume}")

        if not self.cur_os.admin_users:
            p_error("No admin users found in the primary OS. Cannot continue.")
            p_message("If this is a new or freshly reset machine, you will have to go through macOS")
            p_message("initial user set-up and create an admin user before using this installer.")
            sys.exit(1)

    def get_admin_credentials(self):
        if self.credentials_validated:
            return

        print()
        p_message("To continue the installation, you will need to enter your macOS")
        p_message("admin credentials.")
        print()

        if self.sysinfo.boot_mode == "macOS":
            self.admin_user = self.sysinfo.login_user
        else:
            if len(self.cur_os.admin_users) > 1:
                p_question("Choose an admin user for authentication:")
                idx = self.choice("User", self.cur_os.admin_users)
            else:
                idx = 0
            self.admin_user = self.cur_os.admin_users[idx]

        self.admin_password = getpass.getpass(f'Password for {self.admin_user}: ')

    def action_install_into_container(self, avail_parts):
        template = self.choose_os()

        containers = {str(i): p.desc for i,p in enumerate(self.parts) if p in avail_parts}

        print()
        p_question("Choose a container to install into:")
        idx = self.choice("Target container", containers)
        self.part = self.parts[int(idx)]

        ipsw = self.choose_ipsw(template.get("supported_fw", None))
        logging.info(f"Chosen IPSW version: {ipsw.version}")

        self.ins = stub.StubInstaller(self.sysinfo, self.dutil, self.osinfo)
        self.ins.load_ipsw(ipsw)
        self.osins = osinstall.OSInstaller(self.dutil, self.data, template)
        self.osins.load_package()

        self.do_install()

    def action_wipe(self):
        p_warning("This will wipe all data on the currently selected disk.")
        p_warning("Are you sure you want to continue?")
        if not self.yesno("Wipe my disk"):
            return True

        print()

        template = self.choose_os()

        self.osins = osinstall.OSInstaller(self.dutil, self.data, template)
        self.osins.load_package()

        min_size = STUB_SIZE + self.osins.min_size
        print()
        p_message(f"Minimum required space for this OS: {ssize(min_size)}")

        start, end = self.dutil.get_disk_usable_range(self.cur_disk)
        os_size = self.get_os_size_and_info(end - start, min_size, template)

        p_progress(f"Partitioning the whole disk ({self.cur_disk})")
        self.part = self.dutil.partitionDisk(self.cur_disk, "apfs", self.osins.name, STUB_SIZE)

        p_progress(f"Creating new stub macOS named {self.osins.name}")
        logging.info(f"Creating stub macOS: {self.osins.name}")
        self.do_install(os_size)

    def action_install_into_free(self, avail_free):
        template = self.choose_os()

        self.osins = osinstall.OSInstaller(self.dutil, self.data, template)
        self.osins.load_package()

        min_size = STUB_SIZE + self.osins.min_size
        print()
        p_message(f"Minimum required space for this OS: {ssize(min_size)}")

        frees = {str(i): p.desc for i,p in enumerate(self.parts)
                 if p in avail_free and align_down(p.size, PART_ALIGN) >= min_size}

        if len(frees) < 1:
            p_error( "There is not enough free space to install this OS.")
            print()
            p_message("Press enter to go back to the main menu.")
            self.input()
            return True

        if len(frees) > 1:
            print()
            p_question("Choose a free area to install into:")
            idx = self.choice("Target area", frees)
        else:
            idx = list(frees.keys())[0]
        free_part = self.parts[int(idx)]

        print()
        p_message(f"Available free space: {ssize(free_part.size)}")

        os_size = self.get_os_size_and_info(free_part.size, min_size, template)

        p_progress(f"Creating new stub macOS named {self.osins.name}")
        logging.info(f"Creating stub macOS: {self.osins.name}")
        self.part = self.dutil.addPartition(free_part.name, "apfs", self.osins.name, STUB_SIZE)

        self.do_install(os_size)

    def get_os_size_and_info(self, free_size, min_size, template):
        os_size = None
        if self.osins.expandable:
            print()
            p_question("How much space should be allocated to the new OS?")
            p_message("  You can enter a size such as '1GB', a fraction such as '50%',")
            p_message("  the word 'min' for the smallest allowable size, or")
            p_message("  the word 'max' to use all available space.")
            min_perc = 100 * min_size / free_size
            while True:
                os_size = self.get_size("New OS size", default="max",
                                    min=min_size, max=free_size,
                                    total=free_size)
                if os_size is None:
                    continue
                os_size = align_down(os_size, PART_ALIGN)
                if os_size < min_size:
                    p_error(f"Size is too small, please enter a value > {ssize(min_size)} ({min_perc:.2f}%)")
                    continue
                if os_size > free_size:
                    p_error(f"Size is too large, please enter a value < {ssize(free_size)}")
                    continue
                break

            print()
            p_message(f"The new OS will be allocated {ssize(os_size)} of space,")
            p_message(f"leaving {ssize(free_size - os_size)} of free space.")
            os_size -= STUB_SIZE

        print()
        self.flush_input()
        p_question("Enter a name for your OS")
        label = input_prompt(f"OS name ({self.osins.name}): ") or self.osins.name
        self.osins.name = label
        logging.info(f"New OS name: {label}")
        print()

        ipsw = self.choose_ipsw(template.get("supported_fw", None))
        logging.info(f"Chosen IPSW version: {ipsw.version}")
        self.ins = stub.StubInstaller(self.sysinfo, self.dutil, self.osinfo)
        self.ins.load_ipsw(ipsw)
        return os_size

    def action_repair_or_upgrade(self, oses, upgrade):
        choices = {str(i): f"{p.desc}\n      {str(o)}" for i, (p, o) in enumerate(oses)}

        if len(choices) > 1:
            print()
            if upgrade:
                p_question("Choose an existing install to upgrade:")
            else:
                p_question("Choose an incomplete install to repair:")
            idx = self.choice("Installed OS", choices)
        else:
            idx = list(choices.keys())[0]

        self.part, osi = oses[int(idx)]

        if upgrade:
            p_progress(f"Upgrading installation {self.part.name} ({self.part.label})")
            p_info(f"  Old m1n1 stage 1 version: {osi.m1n1_ver}")
            p_info(f"  New m1n1 stage 1 version: {self.m1n1_ver}")
            print()
        else:
            p_progress(f"Resuming installation into {self.part.name} ({self.part.label})")

        self.ins = stub.StubInstaller(self.sysinfo, self.dutil, self.osinfo)
        if not self.ins.check_existing_install(osi):
            op = "upgrade" if upgrade else "repair"
            p_error(   "The existing installation is missing files.")
            p_message(f"This tool can only {op} installations that completed the first")
            p_message( "stage of the installation process. If it was interrupted, please")
            p_message( "delete the partitions manually and reinstall from scratch.")
            return False

        self.dutil.remount_rw(self.ins.osi.system)

        if upgrade:
            # Note: we get the vars out of the boot.bin in the system volume instead of the
            # actual installed fuOS. This is arguably the better option, since it allows
            # users to fix their install using this functionality if they messed up the boot
            # object.
            vars = m1n1.extract_vars(self.ins.boot_obj_path)
            if vars is None:
                p_error("Could not get variables from the installed m1n1")
                p_message(f"Path: {self.ins.boot_obj_path}")
                return False

            p_progress(f"Transferring m1n1 variables:")
            for v in vars:
                p_info(f"  {v}")

            print()
            m1n1.build(self.m1n1, self.ins.boot_obj_path, vars)

        # Unhide the SystemVersion, if hidden
        self.ins.prepare_for_bless()

        # Go for step2 again
        self.step2()

    def do_install(self, total_size=None):
        p_progress(f"Installing stub macOS into {self.part.name} ({self.part.label})")

        self.ins.prepare_volume(self.part)
        self.ins.check_volume()
        self.ins.install_files(self.cur_os)

        self.osins.partition_disk(self.part.name, total_size)

        pkg = None
        if self.osins.needs_firmware:
            os.makedirs("vendorfw", exist_ok=True)
            pkg = asahi_firmware.core.FWPackage("vendorfw")
            self.ins.collect_firmware(pkg)
            pkg.close()
            self.osins.firmware_package = pkg

        self.osins.install(self.ins)

        for i in self.osins.idata_targets:
            self.ins.collect_installer_data(i)
            shutil.copy("installer.log", os.path.join(i, "installer.log"))

        self.step2(report=True)

    def choose_ipsw(self, supported_fw=None):
        sys_iboot = split_ver(self.sysinfo.sys_firmware)
        sys_macos = split_ver(self.sysinfo.macos_ver)
        sys_sfr = split_ver(self.sysinfo.sfr_full_ver)
        chip_min = split_ver(CHIP_MIN_VER.get(self.sysinfo.chip_id, "0"))
        device_min = split_ver(self.device.min_ver)
        minver = [ipsw for ipsw in IPSW_VERSIONS
                 if split_ver(ipsw.version) >= max(chip_min, device_min)
                 and (supported_fw is None or ipsw.version in supported_fw)]
        avail = [ipsw for ipsw in minver
                 if split_ver(ipsw.min_iboot) <= sys_iboot
                 and split_ver(ipsw.min_macos) <= sys_macos
                 and split_ver(ipsw.min_sfr) <= sys_sfr
                 and (not ipsw.expert_only or self.expert)]

        minver.sort(key=lambda ipsw: split_ver(ipsw.version))

        if not avail:
            p_error("Your system firmware is too old.")
            p_error(f"Please upgrade to macOS {minver[0].version} or newer.")
            sys.exit(1)

        if self.expert:
            p_question("Choose the macOS version to use for boot firmware:")
            p_plain("(If unsure, just press enter)")
            p_warning("Picking a non-default option here is UNSUPPORTED and will BREAK YOUR SYSTEM.")
            p_warning("DO NOT FILE BUGS. YOU HAVE BEEN WARNED.")
            idx = self.choice("Version", [i.version for i in avail], len(avail)-1)
        else:
            idx = len(avail)-1

        self.ipsw = ipsw = avail[idx]
        p_message(f"Using macOS {ipsw.version} for OS firmware")
        print()

        return ipsw

    def choose_os(self):
        os_list = self.data["os_list"]
        if not self.expert:
            os_list = [i for i in os_list if not i.get("expert", False)]
        if self.cur_disk != self.sys_disk:
            os_list = [i for i in os_list if i.get("external_boot", False)]
        p_question("Choose an OS to install:")
        idx = self.choice("OS", [i["name"] for i in os_list])
        os = os_list[idx]
        logging.info(f"Chosen OS: {os['name']}")
        return os

    def set_reduced_security(self):
        while True:
            self.get_admin_credentials()
            print()
            p_progress("Preparing the new OS for booting in Reduced Security mode...")
            try:
                subprocess.run(["bputil", "-g", "-v", self.ins.osi.vgid,
                                "-u", self.admin_user, "-p", self.admin_password], check=True)
                break
            except subprocess.CalledProcessError:
                p_error("Failed to run bputil. Press enter to try again.")
                self.input()

        self.credentials_validated = True
        print()

    def bless(self):
        while True:
            self.get_admin_credentials()
            print()
            p_progress("Setting the new OS as the default boot volume...")
            try:
                subprocess.run(["bless", "--setBoot",
                                "--device", "/dev/" + self.ins.osi.sys_volume,
                                "--user", self.admin_user, "--stdinpass"],
                               input=self.admin_password.encode("utf-8"),
                               check=True)
                break
            except subprocess.CalledProcessError:
                if self.admin_password.strip() != self.admin_password:
                    p_warning("Failed to run bless.")
                    p_warning("This is probably because your password starts or ends with a space,")
                    p_warning("and that doesn't work due to a silly Apple bug.")
                    p_warning("Let's try a different way. Sorry, you'll have to type it in again.")
                    try:
                        subprocess.run(["bless", "--setBoot",
                                        "--device", "/dev/" + self.ins.osi.sys_volume,
                                        "--user", self.admin_user], check=True)
                        print()
                        return
                    except subprocess.CalledProcessError:
                        pass
                p_error("Failed to run bless. Press enter to try again.")
                self.input()

        self.credentials_validated = True
        print()

    def step2(self, report=False):
        is_1tr = self.sysinfo.boot_mode == "one true recoveryOS"
        is_recovery = "recoveryOS" in self.sysinfo.boot_mode
        sys_ver = split_ver(self.sysinfo.macos_ver)
        if is_1tr and self.ins.osi.paired:
            subprocess.run([self.ins.step2_sh], check=True)
            self.bless()
            self.step2_completed(report)
        elif is_recovery:
            self.set_reduced_security()
            self.bless()
            self.step2_indirect(report)
        else:
            self.bless()
            self.step2_indirect(report)

    def flush_input(self):
        try:
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        except:
            pass

    def install_info(self, report):
        # Hide the new volume until step2 is done
        self.ins.prepare_for_step2()

        p_success( "Installation successful!")
        print()
        p_progress("Install information:")
        p_info(   f"  APFS VGID: {col()}{self.ins.osi.vgid}")
        if self.osins and self.osins.efi_part:
            p_info(f"  EFI PARTUUID: {col()}{self.osins.efi_part.uuid.lower()}")
        print()

        if report:
            reporting.report(self)

    def step2_completed(self, report=False):
        self.install_info(report)

        print()
        time.sleep(2)
        p_prompt( "Press enter to reboot the system.")
        self.input()
        time.sleep(1)
        os.system("shutdown -r now")

    def step2_indirect(self, report=False):
        # Hide the new volume until step2 is done
        self.ins.prepare_for_step2()

        self.install_info(report)

        p_message( "To be able to boot your new OS, you will need to complete one more step.")
        p_warning( "Please read the following instructions carefully. Failure to do so")
        p_warning( "will leave your new installation in an unbootable state.")
        print()
        p_question( "Press enter to continue.")
        self.input()
        print()
        print()
        print()
        p_message( "When the system shuts down, follow these steps:")
        print()
        p_message( "1. Wait 15 seconds for the system to fully shut down.")
        p_message(f"2. Press and {col(BRIGHT, YELLOW)}hold{col()}{col(BRIGHT)} down the power button to power on the system.")
        p_warning( "   * It is important that the system be fully powered off before this step,")
        p_warning( "     and that you press and hold down the button once, not multiple times.")
        p_warning( "     This is required to put the machine into the right mode.")
        p_message( "3. Release it once you see 'Loading startup options...' or a spinner.")
        p_message( "4. Wait for the volume list to appear.")
        p_message(f"5. Choose '{self.part.label}'.")
        p_message( "6. You will briefly see a 'macOS Recovery' dialog.")
        p_plain(   "   * If you are asked to 'Select a volume to recover',")
        p_plain(   "     then choose your normal macOS volume and click Next.")
        p_plain(   "     You may need to authenticate yourself with your macOS credentials.")
        p_message( "7. Once the 'Asahi Linux installer' screen appears, follow the prompts.")
        print()
        p_warning( "If you end up in a bootloop or get a message telling you that macOS needs to")
        p_warning( "be reinstalled, that means you didn't follow the steps above properly.")
        p_message( "Fully shut down your system without doing anything, and try again.")
        p_message( "If in trouble, hold down the power button to boot, select macOS, run")
        p_message( "this installer again, and choose the 'p' option to retry the process.")
        print()
        time.sleep(2)
        p_prompt( "Press enter to shut down the system.")
        self.input()
        time.sleep(1)
        os.system("shutdown -h now")

    def get_min_free_space(self, p):
        if p.os and any(os.version for os in p.os) and not self.expert:
            logging.info("  Has OS")
            return MIN_FREE_OS
        else:
            return MIN_FREE

    def can_resize(self, p):
        logging.info(f"Checking resizability of {p.name}")
        if p.type != "Apple_APFS":
            logging.info(f"  Not APFS or system container")
            return False

        if p.container is None:
            logging.info(f"  No container?")
            return False

        min_space = self.get_min_free_space(p) + psize("500MB")
        logging.info(f"  Min space required: {min_space}")

        free = p.container["CapacityFree"]
        logging.info(f"  Free space: {free}")
        if free <= min_space:
            logging.info(f"  Cannot resize")
            return False
        else:
            logging.info(f"  Can resize")
            return True

    def action_resize(self, resizable):
        choices = {str(i): p.desc for i,p in enumerate(self.parts) if p in resizable}

        print()
        if len(resizable) > 1 or self.expert:
            p_question("Choose an existing partition to resize:")
            idx = self.choice("Partition", choices)
            target = self.parts[int(idx)]
        else:
            target = resizable[0]

        limits = self.dutil.get_resize_limits(target.name)

        total = target.container["CapacityCeiling"]
        free = target.container["CapacityFree"]
        min_free = self.get_min_free_space(target)
        # Minimum size, ignoring APFS snapshots & co, but with a conservative buffer
        min_size_raw = align_up(total - free + min_free, PART_ALIGN)
        # Minimum size reported by diskutil, considering APFS snapshots & co but with a less conservative buffer
        min_size_safe = limits["MinimumSizePreferred"]
        min_size = max(min_size_raw, min_size_safe)
        overhead = min_size - min_size_raw
        avail = total - min_size

        min_perc = 100 * min_size / total

        assert free > min_free

        p_message( "We're going to resize this partition:")
        p_message(f"  {target.desc}")
        p_info(   f"  Total size: {col()}{ssize(total)}")
        p_info(   f"  Free space: {col()}{ssize(free)}")
        p_info(   f"  Available space: {col()}{ssize(avail)}")
        p_info(   f"  Overhead: {col()}{ssize(overhead)}")
        p_info(   f"  Minimum new size: {col()}{ssize(min_size)} ({min_perc:.2f}%)")
        print()
        if overhead > 1000000000:
            p_warning("  Warning: The selected partition has a large amount of overhead space.")
            p_warning("  This prevents you from resizing the partition to a smaller size, even")
            p_warning("  though macOS reports that space as free.")
            print()
            p_message("  This is usually caused by APFS snapshots used by Time Machine, which")
            p_message("  use up free disk space and block resizing the partition to a smaller")
            p_message("  size. It can also be caused by having a pending macOS upgrade.")
            print()
            p_message("  If you want to resize your partition to a smaller size, please complete")
            p_message("  any pending macOS upgrades and visit this link to learn how to manually")
            p_message("  delete Time Machine snapshots:")
            print()
            p_plain( f"    {col(BLUE, BRIGHT)}https://alx.sh/tmcleanup{col()}")
            print()

            if avail < 2 * PART_ALIGN:
                p_error("  Not enough available space to resize. Please follow the instructions")
                p_error("  above to continue.")
                return False

            if not self.yesno("Continue anyway?"):
                return False
            print()

        if avail < 2 * PART_ALIGN:
            p_error("Not enough available space to resize.")
            return False

        p_question("Enter the new size for your existing partition:")
        p_message( "  You can enter a size such as '1GB', a fraction such as '50%',")
        p_message( "  or the word 'min' for the smallest allowable size.")
        print()
        p_message( "  Examples:")
        p_message( "  30%  - 30% to macOS, 70% to the new OS")
        p_message( "  80GB - 80GB to macOS, the rest to your new OS")
        p_message( "  min  - Shrink macOS as much as (safely) possible")
        print()

        default = "50%"
        if total / 2 < min_size:
            default = "min"
        while True:
            val = self.get_size("New size", default=default, min=min_size, total=total)
            if val is None:
                continue
            val = align_up(val, PART_ALIGN)
            if val < min_size:
                p_error(f"Size is too small, please enter a value > {ssize(min_size)} ({min_perc:.2f}%)")
                continue
            if val >= total:
                p_error(f"Size is too large, please enter a value < {ssize(total)}")
                continue
            freeing = total - val
            print()
            p_message(f"Resizing will free up {ssize(freeing)} of space.")
            if freeing <= MIN_INSTALL_FREE:
                if not self.expert:
                    p_error(f"That's not enough free space for an OS install.")
                    continue
                else:
                    p_warning(f"That's not enough free space for an OS install.")
            print()
            p_message("Note: your system may appear to freeze during the resize.")
            p_message("This is normal, just wait until the process completes.")
            if self.yesno("Continue?"):
                break

        print()
        try:
            self.dutil.resizeContainer(target.name, val)
        except subprocess.CalledProcessError as e:
            print()
            p_error(f"Resize failed. This is usually caused by pre-existing APFS filesystem corruption.")
            p_warning("Carefully read the diskutil logs above for more information about the cause.")
            p_warning("This can usually be solved by doing a First Aid repair from Disk Utility in Recovery Mode.")
            return False

        print()
        p_success(f"Resize complete. Press enter to continue.")
        self.input()
        print()

        return True

    def action_select_disk(self):
        choices = {"1": "Internal storage"}

        for i, disk in enumerate(self.external_disks):
            choices[str(i + 2)] = f"{disk['IORegistryEntryName']} ({ssize(disk['Size'])})"

        print()
        p_question("Choose a disk:")
        idx = int(self.choice("Disk", choices))
        if idx == 1:
            self.cur_disk = self.sys_disk
        else:
            self.cur_disk = self.external_disks[idx - 2]["DeviceIdentifier"]

        return True

    def main(self):
        print()
        p_message("Welcome to the Asahi Linux installer!")
        print()
        p_message("This installer is in an alpha state, and may not work for everyone.")
        p_message("It is intended for developers and early adopters who are comfortable")
        p_message("debugging issues or providing detailed bug reports.")
        print()
        p_message("Please make sure you are familiar with our documentation at:")
        p_plain( f"  {col(BLUE, BRIGHT)}https://alx.sh/w{col()}")
        print()
        p_question("Press enter to continue.")
        self.input()
        print()

        self.expert = False
        if os.environ.get("EXPERT", None):
            p_message("By default, this installer will hide certain advanced options that")
            p_message("are only useful for Asahi Linux developers. You can enable expert mode")
            p_message("to show them. Do not enable this unless you know what you are doing.")
            p_message("Please do not file bugs if things go wrong in expert mode.")
            self.expert = self.yesno("Enable expert mode?")
            print()

        p_progress("Collecting system information...")
        self.sysinfo = system.SystemInfo()
        self.sysinfo.show()
        print()
        self.chip_min_ver = CHIP_MIN_VER.get(self.sysinfo.chip_id, None)
        self.device = DEVICES.get(self.sysinfo.device_class, None)
        if not self.chip_min_ver or not self.device or (self.device.expert_only and not self.expert):
            p_error("This device is not supported yet!")
            p_error("Please check out the Asahi Linux Blog for updates on device support:")
            print()
            p_error("   https://asahilinux.org/blog/")
            print()
            sys.exit(1)

        if self.sysinfo.boot_mode == "macOS" and (
            (not self.sysinfo.login_user)
            or self.sysinfo.login_user == "unknown"):
            p_error("Could not detect logged in user.")
            p_error("Perhaps you are running this installer over SSH?")
            p_error("Please make sure a user is logged into the local console.")
            p_error("You can use SSH as long as there is a local login session.")
            sys.exit(1)

        if self.expert:
            min_ver = MIN_MACOS_VERSION_EXPERT
        else:
            min_ver = MIN_MACOS_VERSION

        if split_ver(self.sysinfo.macos_ver) < split_ver(min_ver):
            p_error("Your macOS version is too old.")
            p_error(f"Please upgrade to macOS {min_ver} or newer.")
            sys.exit(1)

        while self.main_loop():
            pass

    def main_loop(self):
        p_progress("Collecting partition information...")
        self.dutil = diskutil.DiskUtil()
        self.dutil.get_info()
        if self.sys_disk is None:
            self.cur_disk = self.sys_disk = self.dutil.find_system_disk()

        p_info(f"  System disk: {col()}{self.sys_disk}")

        if self.expert:
            self.external_disks = self.dutil.find_external_disks()
        else:
            self.external_disks = None

        if self.external_disks:
            p_info(f"  Found {len(self.external_disks)} external disk(s)")

        self.parts = self.dutil.get_partitions(self.cur_disk)
        print()

        p_progress("Collecting OS information...")
        self.osinfo = osenum.OSEnum(self.sysinfo, self.dutil, self.cur_disk)
        self.osinfo.collect(self.parts)

        parts_free = []
        parts_empty_apfs = []
        parts_resizable = []
        oses_incomplete = []
        oses_upgradable = []

        for i, p in enumerate(self.parts):
            if p.type in ("Apple_APFS_ISC",):
                continue
            if p.free:
                p.desc = f"(free space: {ssize(p.size)})"
                if p.size >= STUB_SIZE:
                    parts_free.append(p)
            elif p.type.startswith("Apple_APFS"):
                p.desc = "APFS"
                if p.type == "Apple_APFS_Recovery":
                    p.desc += " (System Recovery)"
                if p.label is not None:
                    p.desc += f" [{p.label}]"
                if p.container is None:
                    p.desc += f" (not a container)"
                else:
                    vols = p.container["Volumes"]
                    p.desc += f" ({ssize(p.size)}, {len(vols)} volume{'s' if len(vols) != 1 else ''})"
                    if self.can_resize(p):
                        parts_resizable.append(p)
                    else:
                        if p.size >= STUB_SIZE * 0.95:
                            parts_empty_apfs.append(p)
            else:
                p.desc = f"{p.type} ({ssize(p.size)})"

        print()
        if self.cur_disk == self.sys_disk:
            t = "system"
        else:
            t = "external"
        p_message(f"Partitions in {t} disk ({self.cur_disk}):")

        if self.cur_disk == self.sys_disk:
            self.cur_os = None
        self.is_sfr_recovery = self.sysinfo.boot_vgid in (osenum.UUID_SROS, osenum.UUID_FROS)
        default_os = None

        r = col(YELLOW) + "R" + col()
        b = col(GREEN) + "B" + col()
        u = col(RED) + "?" + col()
        d = col(BRIGHT) + "*" + col()

        is_gpt = self.dutil.disks[self.cur_disk]["Content"] == "GUID_partition_scheme"

        for i, p in enumerate(self.parts):
            if p.desc is None:
                continue
            p_choice(f"  {col(BRIGHT)}{i}{col()}: {p.desc}")
            if not p.os:
                continue
            for os in p.os:
                if not os.version:
                    continue
                state = " "
                if self.sysinfo.boot_vgid == os.vgid and self.sysinfo.boot_uuid == os.rec_vgid:
                    if p.type == "APFS":
                        self.cur_os = os
                    state = r
                elif self.sysinfo.boot_uuid == os.vgid:
                    self.cur_os = os
                    state = b
                elif self.sysinfo.boot_vgid == os.vgid:
                    state = u
                if self.sysinfo.default_boot == os.vgid:
                    default_os = os
                    state += d
                else:
                    state += " "
                p_plain(f"    OS: [{state}] {os}")
                if os.stub and os.m1n1_ver and os.m1n1_ver != self.m1n1_ver:
                    oses_upgradable.append((p, os))
                elif os.stub and not (os.bp and os.bp.get("coih", None)):
                    oses_incomplete.append((p, os))

        print()
        p_plain(f"  [{b} ] = Booted OS, [{r} ] = Booted recovery, [{u} ] = Unknown")
        p_plain(f"  [ {d}] = Default boot volume")
        print()

        if self.cur_os is None and self.sysinfo.boot_mode != "macOS":
            self.cur_os = default_os
        self.check_cur_os()

        actions = {}

        default = None
        if oses_incomplete:
            actions["p"] = "Repair an incomplete installation"
            default = default or "p"
        if parts_free and is_gpt:
            actions["f"] = "Install an OS into free space"
            default = default or "f"
        if parts_empty_apfs and is_gpt and False: # This feature is confusing, disable it for now
            actions["a"] = "Install an OS into an existing APFS container"
        if parts_resizable and is_gpt:
            actions["r"] = "Resize an existing partition to make space for a new OS"
            default = default or "r"
        if self.cur_disk != self.sys_disk:
            actions["w"] = "Wipe and install into the whole disk"
            # Never make this default!
        if self.external_disks:
            actions["d"] = "Select another disk for installation"
            default = default or "d"
        if oses_upgradable:
            actions["m"] = "Upgrade m1n1 on an existing OS"
            default = default or "m"

        if not actions:
            p_error("No actions available on this system.")
            p_message("No partitions have enough free space to be resized, and there is")
            p_message("nothing else to be done.")
            sys.exit(1)

        actions["q"] = "Quit without doing anything"
        default = default or "q"

        print()
        p_question("Choose what to do:")
        act = self.choice("Action", actions, default)

        if act == "f":
            return self.action_install_into_free(parts_free)
        elif act == "a":
            return self.action_install_into_container(parts_empty_apfs)
        elif act == "r":
            return self.action_resize(parts_resizable)
        elif act == "m":
            return self.action_repair_or_upgrade(oses_upgradable, upgrade=True)
        elif act == "p":
            return self.action_repair_or_upgrade(oses_incomplete, upgrade=False)
        elif act == "d":
            return self.action_select_disk()
        elif act == "w":
            return self.action_wipe()
        elif act == "q":
            return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                        datefmt='%m-%d %H:%M',
                        filename='installer.log',
                        filemode='w')

    console = logging.StreamHandler()
    console.setLevel(logging.ERROR)
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)
    logging.info("Startup")

    logging.info("Environment:")
    for var in ("INSTALLER_BASE", "INSTALLER_DATA", "REPO_BASE", "IPSW_BASE", "EXPERT", "REPORT", "REPORT_TAG"):
        logging.info(f"  {var}={os.environ.get(var, None)}")

    try:
        installer_version = open("version.tag", "r").read().strip()
        logging.info(f"Version: {installer_version}")
        InstallerMain(installer_version).main()
    except KeyboardInterrupt:
        print()
        logging.info("KeyboardInterrupt")
        p_error("Interrupted")
    except subprocess.CalledProcessError as e:
        cmd = shlex.join(e.cmd)
        p_error(f"Failed to run process: {cmd}")
        if e.output is not None:
            p_error(f"Output: {e.output}")
        logging.exception("Process execution failed")
        p_warning("If you need to file a bug report, please attach the log file:")
        p_warning(f"  {os.getcwd()}/installer.log")
    except Exception:
        logging.exception("Exception caught")
        p_warning("If you need to file a bug report, please attach the log file:")
        p_warning(f"  {os.getcwd()}/installer.log")
