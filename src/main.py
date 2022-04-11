#!/usr/bin/python3
# SPDX-License-Identifier: MIT
import os, os.path, shlex, subprocess, sys, time, termios, json, getpass
from dataclasses import dataclass

import system, osenum, stub, diskutil, osinstall, firmware
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
MIN_MACOS_VERSION_EXPERT = "12.1"


@dataclass
class IPSW:
    version: str
    min_macos: str
    min_iboot: str
    paired_sfr: bool
    url: str


CHIP_MIN_VER = {
    0x8103: "11.0",  # T8103, M1
    0x6000: "12.0",  # T6000, M1 Pro
    0x6001: "12.0",  # T6001, M1 Max
    # Not yet
    # 0x6002: "12.3"      # T6002, M1 Ultra
}

DEVICE_MIN_VER = {
    "j274ap": "11.0",  # Mac mini (M1, 2020)
    "j293ap": "11.0",  # MacBook Pro (13-inch, M1, 2020)
    "j313ap": "11.0",  # MacBook Air (M1, 2020)
    "j456ap": "11.3",  # iMac (24-inch, M1, 2021)
    "j457ap": "11.3",  # iMac (24-inch, M1, 2021)
    "j314cap": "12.0",  # MacBook Pro (14-inch, M1 Max, 2021)
    "j314sap": "12.0",  # MacBook Pro (14-inch, M1 Pro, 2021)
    "j316cap": "12.0",  # MacBook Pro (16-inch, M1 Max, 2021)
    "j316sap": "12.0",  # MacBook Pro (16-inch, M1 Pro, 2021)
    # Not yet
    # "j375cap": "12.3",  # Mac Studio (M1 Max, 2022)
    # "j375dap": "12.3",  # Mac Studio (M1 Ultra, 2022)
}

IPSW_VERSIONS = [
    IPSW("12.1",
         "12.1",
         "iBoot-7429.61.2",
         False,
         "https://updates.cdn-apple.com/2021FCSWinter/fullrestores/002-42433/F3F6D5CD-67FE-449C-9212-F7409808B6C4/UniversalMac_12.1_21C52_Restore.ipsw"),
    IPSW("12.3",
         "12.1",
         "iBoot-7459.101.2",
         False,
         "https://updates.cdn-apple.com/2022SpringFCS/fullrestores/071-08757/74A4F2A1-C747-43F9-A22A-C0AD5FB4ECB6/UniversalMac_12.3_21E230_Restore.ipsw"),
]


class InstallerMain:
    def __init__(self):
        self.data = json.load(open("installer_data.json"))
        self.credentials_validated = False
        self.expert = False
        self.admin_user = None
        self.admin_password = None
        self.part = None
        self.ins = None
        self.osins = None
        self.ipsw = None
        self.dutil = None
        self.sysdsk = None
        self.parts = None
        self.osinfo = None

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
            options = {str(i + 1): v for i, v in enumerate(options)}
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

        containers = {str(i): p.desc for i, p in enumerate(self.parts) if p in avail_parts}

        print()
        p_question("Choose a container to install into:")
        idx = self.choice("Target container", containers)
        self.part = self.parts[int(idx)]

        ipsw = self.choose_ipsw(template.get("supported_fw", None))
        logging.info(f"Chosen IPSW version: {ipsw.version}")

        self.ins = stub.StubInstaller(self.sysinfo, self.dutil, self.osinfo, ipsw)
        self.osins = osinstall.OSInstaller(self.dutil, self.data, template)
        self.osins.load_package()

        self.do_install()

    def action_install_into_free(self, avail_free):
        template = self.choose_os()

        self.osins = osinstall.OSInstaller(self.dutil, self.data, template)
        self.osins.load_package()

        min_size = STUB_SIZE + self.osins.min_size
        print()
        p_message(f"Minimum required space for this OS: {ssize(min_size)}")

        frees = {str(i): p.desc for i, p in enumerate(self.parts)
                 if p in avail_free and align_down(p.size, PART_ALIGN) >= min_size}

        if len(frees) < 1:
            p_error("There is not enough free space to install this OS.")
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

        os_size = None
        if self.osins.expandable:
            print()
            p_question("How much space should be allocated to the new OS?")
            p_message("  You can enter a size such as '1GB', a fraction such as '50%',")
            p_message("  the word 'min' for the smallest allowable size, or")
            p_message("  the word 'max' to use all available space.")
            min_perc = 100 * min_size / free_part.size
            while True:
                os_size = self.get_size("New OS size", default="max",
                                        min=min_size, max=free_part.size,
                                        total=free_part.size)
                if os_size is None:
                    continue
                os_size = align_down(os_size, PART_ALIGN)
                if os_size < min_size:
                    p_error(f"Size is too small, please enter a value > {ssize(min_size)} ({min_perc:.2f}%)")
                    continue
                if os_size >= free_part.size:
                    p_error(f"Size is too large, please enter a value < {ssize(free_part.size)}")
                    continue
                break

            print()
            p_message(f"The new OS will be allocated {ssize(os_size)} of space,")
            p_message(f"leaving {ssize(free_part.size - os_size)} of free space.")
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
        self.ins = stub.StubInstaller(self.sysinfo, self.dutil, self.osinfo, ipsw)

        p_progress(f"Creating new stub macOS named {label}")
        logging.info(f"Creating stub macOS: {label}")
        self.part = self.dutil.addPartition(free_part.name, "apfs", label, STUB_SIZE)

        self.do_install(os_size)

    def do_install(self, total_size=None):
        p_progress(f"Installing stub macOS into {self.part.name} ({self.part.label})")

        self.ins.prepare_volume(self.part)
        self.ins.check_volume()
        self.ins.install_files(self.cur_os)

        self.osins.partition_disk(self.part.name, total_size)

        pkg = None
        if self.osins.needs_firmware:
            pkg = firmware.FWPackage("firmware.tar")
            self.ins.collect_firmware(pkg)
            pkg.close()
            self.osins.firmware_package = pkg

        self.osins.install(self.ins.boot_obj_path)

        for i in self.osins.idata_targets:
            self.ins.collect_installer_data(i)
            shutil.copy("installer.log", os.path.join(i, "installer.log"))

        self.step2()

    def choose_ipsw(self, supported_fw=None):
        sys_iboot = split_ver(self.sysinfo.sys_firmware)
        sys_macos = split_ver(self.sysinfo.macos_ver)
        chip_min = split_ver(CHIP_MIN_VER.get(self.sysinfo.chip_id, "0"))
        device_min = split_ver(DEVICE_MIN_VER.get(self.sysinfo.device_class, "0"))
        minver = [ipsw for ipsw in IPSW_VERSIONS
                  if split_ver(ipsw.version) >= max(chip_min, device_min)
                  and (supported_fw is None or ipsw.version in supported_fw)]
        avail = [ipsw for ipsw in minver
                 if split_ver(ipsw.min_iboot) <= sys_iboot
                 and split_ver(ipsw.min_macos) <= sys_macos]

        if not avail:
            p_error("Your system firmware is too old.")
            p_error(f"Please upgrade to macOS {minver[0].version} or newer.")
            sys.exit(1)

        if self.expert:
            p_question("Choose the macOS version to use for boot firmware:")
            p_plain("(If unsure, just press enter)")
            idx = self.choice("Version", [i.version for i in avail], len(avail) - 1)
        else:
            idx = len(avail) - 1

        self.ipsw = ipsw = avail[idx]
        p_message(f"Using macOS {ipsw.version} for OS firmware")
        print()

        return ipsw

    def choose_os(self):
        os_list = self.data["os_list"]
        if not self.expert:
            os_list = [i for i in os_list if not i.get("expert", False)]
        p_question("Choose an OS to install:")
        idx = self.choice("OS", [i["name"] for i in os_list])
        operating_system = os_list[idx]
        logging.info(f"Chosen OS: {operating_system['name']}")
        return operating_system

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

    def step2(self):
        is_1tr = self.sysinfo.boot_mode == "one true recoveryOS"
        is_recovery = "recoveryOS" in self.sysinfo.boot_mode
        bootpicker_works = split_ver(self.sysinfo.macos_ver) >= split_ver(self.ipsw.min_macos)

        if is_1tr and self.is_sfr_recovery and self.ipsw.paired_sfr:
            subprocess.run([self.ins.step2_sh], check=True)
            self.startup_disk(recovery=True, volume_blessed=True, reboot=True)
        elif is_recovery:
            self.set_reduced_security()
            self.startup_disk(recovery=True, volume_blessed=True)
            self.step2_indirect()
        elif bootpicker_works:
            self.startup_disk()
            self.step2_indirect()
        else:
            assert False  # should never happen, we don't give users the option

    def step2_1tr_direct(self):
        self.startup_disk_recovery()
        subprocess.run([self.ins.step2_sh], check=True)

    def step2_ros_indirect(self):
        self.startup_disk_recovery()

    def flush_input(self):
        try:
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        except:
            pass

    def step2_indirect(self):
        # Hide the new volume until step2 is done
        os.rename(self.ins.systemversion_path,
                  self.ins.systemversion_path.replace("SystemVersion.plist",
                                                      "SystemVersion-disabled.plist"))

        p_success("Installation successful!")
        print()
        p_progress("Install information:")
        p_info(f"  APFS VGID: {col()}{self.ins.osi.vgid}")
        if self.osins.efi_part:
            p_info(f"  EFI PARTUUID: {col()}{self.osins.efi_part.uuid.lower()}")
        print()
        p_message("To be able to boot your new OS, you will need to complete one more step.")
        p_warning("Please read the following instructions carefully. Failure to do so")
        p_warning("will leave your new installation in an unbootable state.")
        print()
        p_question("Press enter to continue.")
        self.input()
        print()
        print()
        print()
        p_message("When the system shuts down, follow these steps:")
        print()
        p_message("1. Wait 15 seconds for the system to fully shut down.")
        p_message(
            f"2. Press and {col(BRIGHT, YELLOW)}hold{col()}{col(BRIGHT)} down the power button to power on the system.")
        p_warning("   * It is important that the system be fully powered off before this step,")
        p_warning("     and that you press and hold down the button once, not multiple times.")
        p_warning("     This is required to put the machine into the right mode.")
        p_message("3. Release it once 'Entering startup options' is displayed,")
        p_message("   or you see a spinner.")
        p_message("4. Wait for the volume list to appear.")
        p_message(f"5. Choose '{self.part.label}'.")
        p_message("6. You will briefly see a 'macOS Recovery' dialog.")
        p_plain("   * If you are asked to 'Select a volume to recover',")
        p_plain("     then choose your normal macOS volume and click Next.")
        p_plain("     You may need to authenticate yourself with your macOS credentials.")
        p_message("7. Once the 'Asahi Linux installer' screen appears, follow the prompts.")
        print()
        time.sleep(2)
        p_prompt("Press enter to shut down the system.")
        self.input()
        time.sleep(1)
        os.system("shutdown -h now")

    def startup_disk(self, recovery=False, volume_blessed=False, reboot=False):
        if split_ver(self.sysinfo.macos_ver) >= (12, 3):
            # Rejoice!
            return self.bless()

        print()
        p_message(f"When the Startup Disk screen appears, choose '{self.part.label}', then click Restart.")
        if not volume_blessed:
            p_message("You will have to authenticate yourself.")
        print()
        p_prompt("Press enter to continue.")
        self.input()

        if recovery:
            args = ["/System/Applications/Utilities/Startup Disk.app/Contents/MacOS/Startup Disk"]
        else:
            os.system("killall -9 'System Preferences' 2>/dev/null")
            os.system("killall -9 storagekitd 2>/dev/null")
            time.sleep(0.5)
            args = ["sudo", "-u", self.sysinfo.login_user,
                    "open", "-b", "com.apple.systempreferences",
                    "/System/Library/PreferencePanes/StartupDisk.prefPane"]

        sd = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not recovery:
            # Sometimes this doesn't open the right PrefPane and we need to do it twice (?!)
            sd.wait()
            time.sleep(0.5)
            sd = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cur_vol = self.sysinfo.default_boot

        # This race is tight... I hate this.
        if not reboot:
            while self.sysinfo.default_boot == cur_vol:
                self.sysinfo.get_nvram_data()

            if recovery:
                sd.kill()
            else:
                os.system("killall -9 StartupDiskPrefPaneService 'System Preferences' 2>/dev/null")
                sd.wait()

            print()

    def get_min_free_space(self, p):
        if p.os and any(os.version for os in p.os) and not self.expert:
            logging.info("  Has OS")
            return MIN_FREE_OS
        else:
            return MIN_FREE

    def can_resize(self, p):
        logging.info(f"Checking resizability of {p.name}")
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
        choices = {str(i): p.desc for i, p in enumerate(self.parts) if p in resizable}

        print()
        if len(resizable) > 1 or self.expert:
            p_question("Choose an existing partition to resize:")
            idx = self.choice("Partition", choices)
            target = self.parts[int(idx)]
        else:
            target = resizable[0]

        total = target.container["CapacityCeiling"]
        free = target.container["CapacityFree"]
        min_free = self.get_min_free_space(target)
        min_size = align_up(total - free + min_free, PART_ALIGN)
        min_perc = 100 * min_size / total

        assert free > min_free

        p_message("We're going to resize this partition:")
        p_message(f"  {target.desc}")
        p_info(f"  Total size: {col()}{ssize(total)}")
        p_info(f"  Free space: {col()}{ssize(free)}")
        p_info(f"  Minimum free space: {col()}{ssize(min_free)}")
        p_info(f"  Minimum total size: {col()}{ssize(min_size)} ({min_perc:.2f}%)")
        print()
        p_question("Enter the new size for your existing partition:")
        p_message("  You can enter a size such as '1GB', a fraction such as '50%',")
        p_message("  or the word 'min' for the smallest allowable size.")
        print()
        p_message("  Examples:")
        p_message("  30%  - 30% to macOS, 70% to the new OS")
        p_message("  80GB - 80GB to macOS, the rest to your new OS")
        p_message("  min  - Shrink macOS as much as (safely) possible")
        print()

        default = "50%"
        if total / 2 < min_size:
            default = "min"
        while True:
            val = self.get_size("New size", default=default, min=min_size, total=total)
            if val is None:
                continue
            val = align_down(val, PART_ALIGN)
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
        self.dutil.resizeContainer(target.name, val)

        print()
        p_success(f"Resize complete. Press enter to continue.")
        self.input()
        print()

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
        p_plain(f"  {col(BLUE, BRIGHT)}https://alx.sh/w{col()}")
        print()
        p_question("Press enter to continue.")
        self.input()
        print()
        p_message("By default, this installer will hide certain advanced options that")
        p_message("are only useful for developers. You can enable expert mode to show them.")
        self.expert = self.yesno("Enable expert mode?")
        print()

        p_progress("Collecting system information...")
        self.sysinfo = system.SystemInfo()
        self.sysinfo.show()
        print()
        if (self.sysinfo.chip_id not in CHIP_MIN_VER or
                self.sysinfo.device_class not in DEVICE_MIN_VER):
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
        self.sysdsk = self.dutil.find_system_disk()
        p_info(f"  System disk: {col()}{self.sysdsk}")
        self.parts = self.dutil.get_partitions(self.sysdsk)
        print()

        p_progress("Collecting OS information...")
        self.osinfo = osenum.OSEnum(self.sysinfo, self.dutil, self.sysdsk)
        self.osinfo.collect(self.parts)

        parts_free = []
        parts_empty_apfs = []
        parts_resizable = []

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
        p_message(f"Partitions in system disk ({self.sysdsk}):")

        self.cur_os = None
        self.is_sfr_recovery = self.sysinfo.boot_vgid in (osenum.UUID_SROS, osenum.UUID_FROS)
        default_os = None

        r = col(YELLOW) + "R" + col()
        b = col(GREEN) + "B" + col()
        u = col(RED) + "?" + col()
        d = col(BRIGHT) + "*" + col()

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

        print()
        p_plain(f"  [{b} ] = Booted OS, [{r} ] = Booted recovery, [{u} ] = Unknown")
        p_plain(f"  [ {d}] = Default boot volume")
        print()

        if self.cur_os is None and self.sysinfo.boot_mode != "macOS":
            self.cur_os = default_os
        self.check_cur_os()

        actions = {}

        default = None
        if parts_free:
            actions["f"] = "Install an OS into free space"
            default = default or "f"
        if parts_empty_apfs and False:  # This feature is confusing, disable it for now
            actions["a"] = "Install an OS into an existing APFS container"
        if parts_resizable:
            actions["r"] = "Resize an existing partition to make space for a new OS"
            default = default or "r"
        if self.sysinfo.boot_mode == "one true recoveryOS" and False:
            actions["m"] = "Upgrade bootloader of an existing OS"

        if not actions:
            p_error("No actions available on this system.")
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
            p_error("Unimplemented")
            sys.exit(1)
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
    for var in ("INSTALLER_BASE", "INSTALLER_DATA", "REPO_BASE", "IPSW_BASE"):
        logging.info(f"  {var}={os.environ.get(var, None)}")

    try:
        installer_version = open("version.tag", "r").read()
        logging.info(f"Version: {installer_version}")
        InstallerMain().main()
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
    except:
        logging.exception("Exception caught")
        p_warning("If you need to file a bug report, please attach the log file:")
        p_warning(f"  {os.getcwd()}/installer.log")
