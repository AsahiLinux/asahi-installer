#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
import os, os.path, shlex, subprocess, sys, time, termios, json, getpass
from dataclasses import dataclass

import core.asahi_firmware as asahi_firmware
import core.bugs as bugs
import core.diskutil as diskutil
import core.m1n1 as m1n1
import core.osenum as osenum
import core.osinstall as osinstall
import core.reporting as reporting
import core.stub as stub
import core.system as system

from core.installer import *
from core.exceptions import *
from core.util import *
from terminal import *

class InstallerCLI(InstallerCore):
    ACTION_KEYS = {
        ACTION_REPAIR: "p",
        ACTION_INSTALL_FREE: "f",
        ACTION_INSTALL_CONTAINER: "a",
        ACTION_RESIZE: "r",
        ACTION_WIPE: "w",
        ACTION_SELECT_DISK: "d",
        ACTION_UPGRADE: "m",
        ACTION_VENDORFW: "v",
        ACTION_VOLBOOTABLE: "7",
    }

    ACTION_LABELS = {
        ACTION_REPAIR: "Repair an incomplete installation",
        ACTION_INSTALL_FREE: "Install an OS into free space",
        ACTION_INSTALL_CONTAINER: "Install an OS into an existing APFS container",
        ACTION_RESIZE: "Resize an existing partition to make space for a new OS",
        ACTION_WIPE: "Wipe and install into the whole disk",
        ACTION_SELECT_DISK: "Select another disk for installation",
        ACTION_UPGRADE: "Upgrade m1n1 on an existing OS",
        ACTION_VENDORFW: "Rebuild vendor firmware package",
        ACTION_VOLBOOTABLE: "Fix macOS 27 boot picker compatibility",
    }

    def __init__(self, version):
        super().__init__(version, terminal_progress, "-v" in sys.argv)
        attach_log_handler()

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
        try:
            self.os_valid()
        except OSInvalidError:
            p_error("Unable to determine primary OS.")
            p_error("This installer requires you to already have a macOS install with")
            p_error("at least one administrator user that is a machine owner.")
            p_error("Please run this installer from your main macOS instance or its")
            p_error("paired recovery, or ensure the default boot volume is set correctly.")
            sys.exit(1)

        p_progress(f"Using OS '{self.cur_os.label}' ({self.cur_os.sys_volume}) for machine authentication.")
        logging.info(f"Current OS: {self.cur_os.label} / {self.cur_os.sys_volume}")

        preboot_updated = False

        while True:
            try:
                self.user_valid()
                break
            except (NoAdminUsersError, UserNotAdminError) as e:
                if not preboot_updated:
                    p_message(f"Oops, your Preboot volume may be out of date. Fixing that for you...")
                    self.update_preboot()
                    p_message(f"Preboot volume updated.")
                    preboot_updated = True
                    continue

                if isinstance(e, NoAdminUsersError):
                    p_error("No admin users found in the primary OS. Cannot continue.")
                    p_message("If this is a new or freshly reset machine, you will have to go through macOS")
                    p_message("initial user set-up and create an admin user before using this installer.")
                else:
                    p_error(f"Your login user {self.sysinfo.login_user} is not a machine admin.")
                    print()
                    p_info(f"These users are machine admins: {' '.join(self.cur_os.admin_users)}")
                    print()
                    p_message(f"You have to be a machine admin to install {DISTRO}.")
                sys.exit(1)

    def get_admin_credentials(self):
        if self.credentials_validated:
            return

        print()
        p_message("To continue the installation, you will need to enter your macOS")
        p_message("admin credentials.")
        print()

        users = self.admin_candidates()
        if len(users) > 1:
            p_question("Choose an admin user for authentication:")
            idx = self.choice("User", users)
        else:
            idx = 0
        user = users[idx]

        password = getpass.getpass(f'Password for {user}: ')
        self.set_admin_credentials(user, password)

    def action_install_into_container(self, avail_parts):
        template = self.choose_os()

        containers = {str(i): p.desc for i,p in enumerate(self.partitions) if p in avail_parts}

        print()
        p_question("Choose a container to install into:")
        idx = self.choice("Target container", containers)
        part = self.partitions[int(idx)]

        self.load_ipsw(self.choose_ipsw(template.get("supported_fw", None)))
        self.load_os_package(template)

        self.install_into_container(part)
        self.step2(report=True)

    def action_wipe(self):
        p_warning("This will wipe all data on the currently selected disk.")
        p_warning("Are you sure you want to continue?")
        if not self.yesno("Wipe my disk"):
            return True

        print()

        template = self.choose_os()

        self.load_os_package(template)

        min_size = self.min_os_size()
        print()
        p_message(f"Minimum required space for this OS: {ssize(min_size)}")

        start, end = self.dutil.get_disk_usable_range(self.cur_disk)
        os_size = self.get_os_size_and_info(end - start, min_size, template)

        self.install_into_disk(os_size)
        self.step2(report=True)

    def action_install_into_free(self):
        template = self.choose_os()

        self.load_os_package(template)

        min_size = self.min_os_size()
        print()
        p_message(f"Minimum required space for this OS: {ssize(min_size)}")

        frees = {str(p.index): p.desc for p in self.usable_free_areas(min_size)}

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
        free_part = self.partitions[int(idx)]

        print()
        p_message(f"Available free space: {ssize(free_part.size)}")

        os_size = self.get_os_size_and_info(free_part.size, min_size, template)

        self.install_into_free(free_part, os_size)
        self.step2(report=True)

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
                try:
                    os_size = self.check_os_size(os_size, min_size, free_size)
                except SizeTooSmallError as e:
                    p_error(f"Size is too small, please enter a value > {ssize(e.limit)} ({min_perc:.2f}%)")
                    continue
                except SizeTooLargeError as e:
                    p_error(f"Size is too large, please enter a value < {ssize(e.limit)}")
                    continue
                break

            print()
            p_message(f"The new OS will be allocated {ssize(os_size)} of space,")
            p_message(f"leaving {ssize(free_size - os_size)} of free space.")

        print()
        self.flush_input()
        p_question("Enter a name for your OS")
        label = input_prompt(f"OS name ({self.osins.name}): ") or self.osins.name
        self.osins.name = label
        logging.info(f"New OS name: {label}")
        print()

        self.load_ipsw(self.choose_ipsw(template.get("supported_fw", None)))
        return os_size

    def action_repair_or_upgrade(self, oses, upgrade):
        choices = {str(i): f"{p.desc}\n      {describe_os(o)}" for i, (p, o) in enumerate(oses)}

        if len(choices) > 1:
            print()
            if upgrade:
                p_question("Choose an existing install to upgrade:")
            else:
                p_question("Choose an incomplete install to repair:")
            idx = self.choice("Installed OS", choices)
        else:
            idx = list(choices.keys())[0]

        part, osi = oses[int(idx)]

        if upgrade:
            p_progress(f"Upgrading installation {part.name} ({part.label})")
            p_info(f"  Old m1n1 stage 1 version: {osi.m1n1_ver}")
            p_info(f"  New m1n1 stage 1 version: {self.m1n1_ver}")
            print()
        else:
            p_progress(f"Resuming installation into {part.name} ({part.label})")

        try:
            self.repair_install(part, osi, upgrade)
        except ExistingInstallError:
            op = "upgrade" if upgrade else "repair"
            p_error(   "The existing installation is missing files.")
            p_message(f"This tool can only {op} installations that completed the first")
            p_message( "stage of the installation process. If it was interrupted, please")
            p_message( "delete the partitions manually and reinstall from scratch.")
            return False
        except M1n1VarsError as e:
            p_error("Could not get variables from the installed m1n1")
            p_message(f"Path: {e.path}")
            return False

        # Go for step2 again
        self.step2()

    def action_set_vol_bootable(self, oses):
        choices = {str(i): f"{p.desc}\n      {describe_os(o)}" for i, (p, o) in enumerate(oses)}

        if len(choices) > 1:
            print()
            p_question("Choose an install to fix macOS 27 compatibility on:")
            idx = self.choice("Installed OS", choices)
        else:
            idx = list(choices.keys())[0]

        part, osi = oses[int(idx)]
        self.set_vol_bootable(part, osi)

        print()
        p_success(f"macOS 27 fix applied. System Settings caches the bootability state,")
        p_success(f"so you may need to reboot before the os becomes visible")
        p_success(f"Press enter to continue.")
        self.input()
        print()

        return True

    def action_rebuild_vendorfw(self, oses):
        choices = {str(i): f"{p.desc}\n      {describe_os(o)}" for i, (p, o) in enumerate(oses)}

        if len(choices) > 1:
            print()
            p_question("Choose an install to rebuild firmware for:")
            idx = self.choice("Installed OS", choices)
        else:
            idx = list(choices.keys())[0]

        part, osi = oses[int(idx)]
        try:
            self.rebuild_vendorfw(part, osi)
        except ExistingInstallError:
            p_error(   "The existing installation is missing files.")
            p_message(f"This tool can only rebuild firmware on installations that completed the first")
            p_message( "stage of the installation process. If it was interrupted, please")
            p_message( "delete the partitions manually and reinstall from scratch.")
            return False
        except M1n1VarsError as e:
            p_error("Could not get variables from the installed m1n1")
            p_message(f"Path: {e.path}")
            return False
        except EspNotFoundError:
            p_error("Unable to determine the associated EFI system partition for this install.")
            p_message("Is first stage m1n1 corrupted?")
            return False
        except UnsupportedVersionError as e:
            p_error(f"This install is using an unsupported macOS version {e.version}")
            p_message("Unable to rebuild firmware")
            return False

        print()
        p_success(f"Firmware rebuild complete. Press enter to continue.")
        self.input()
        print()

        return True

    def choose_ipsw(self, supported_fw=None):
        try:
            avail = self.available_ipsws(supported_fw)
        except FirmwareTooOldError as e:
            p_error("Your system firmware is too old.")
            p_error(f"Please upgrade to macOS {e.min_version} or newer.")
            sys.exit(1)

        if self.expert:
            p_question("Choose the macOS version to use for boot firmware:")
            p_plain("(If unsure, just press enter)")
            p_warning("Picking a non-default option here is UNSUPPORTED and will BREAK YOUR SYSTEM.")
            p_warning("DO NOT FILE BUGS. YOU HAVE BEEN WARNED.")
            idx = self.choice("Version", [i.version for i in avail], len(avail)-1)
        else:
            idx = len(avail)-1

        ipsw = avail[idx]
        p_message(f"Using macOS {ipsw.version} for OS firmware")
        print()

        return ipsw

    def choose_os(self):
        os_list = self.available_oses()
        p_question("Choose an OS to install:")
        idx = self.choice("OS", [i["name"] for i in os_list])
        os = os_list[idx]
        logging.info(f"Chosen OS: {os['name']}")
        return os

    def do_reduced_security(self):
        while True:
            self.get_admin_credentials()
            print()
            p_progress("Preparing the new OS for booting in Reduced Security mode...")
            try:
                self.set_reduced_security()
                break
            except subprocess.CalledProcessError:
                p_error("Failed to run bputil. Press enter to try again.")
                self.input()

        print()

    def do_bless(self):
        while True:
            self.get_admin_credentials()
            print()
            p_progress("Setting the new OS as the default boot volume...")
            try:
                self.bless()
                break
            except subprocess.CalledProcessError:
                if self.admin_password.strip() != self.admin_password:
                    p_warning("Failed to run bless.")
                    p_warning("This is probably because your password starts or ends with a space,")
                    p_warning("and that doesn't work due to a silly Apple bug.")
                    p_warning("Let's try a different way. Sorry, you'll have to type it in again.")
                    try:
                        self.bless(use_stdin=False)
                        print()
                        return
                    except subprocess.CalledProcessError:
                        pass
                p_error("Failed to run bless. Press enter to try again.")
                self.input()

        print()

    def step2(self, report=False):
        mode = self.step2_mode()
        if mode == STEP2_DIRECT:
            self.run_step2_script()
            self.do_bless()
            self.step2_completed(report)
        elif mode == STEP2_RECOVERY:
            self.do_reduced_security()
            self.do_bless()
            self.step2_indirect(report)
        else:
            self.do_bless()
            self.step2_indirect(report)

    def flush_input(self):
        try:
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        except:
            pass

    def install_info(self, report):
        self.hide_new_volume()
        info = self.get_install_info()

        p_success( "Installation successful!")
        print()
        p_progress("Install information:")
        p_info(   f"  APFS VGID: {col()}{info.vgid}")
        if info.efi_partuuid:
            p_info(f"  EFI PARTUUID: {col()}{info.efi_partuuid}")
        print()

        if report:
            self.report()

    def show_report_data(self, data):
        print()
        p_message(f"This is the data that will be sent:")

        for line in json.dumps(data, indent=4).split("\n"):
            if not line:
                continue
            for key, exp in reporting.EXPLANATIONS.items():
                indent = line[:len(line) - len(line.lstrip())]
                if line.strip().startswith(f'"{key}"'):
                    exp = indent + exp.replace("\n", "\n" + indent)
                    p_message(exp)
                    break
            p_info(line)
        print()

    def report_inner(self, url, tag):
        data = reporting.build_report(self, tag)

        print()
        print()
        p_question("Help us improve Asahi Linux!")
        p_message("We'd love to know how many people are installing Asahi and on what")
        p_message("kind of hardware. Would you mind sending a one-time installation")
        p_message("report to us?")
        print()
        p_warning("This will only report what kind of machine you have, the OS you're")
        p_warning("installing, basic version info, and the rough install size.")
        p_warning("No personally identifiable information (such as serial numbers,")
        p_warning("specific partition sizes, etc.) is included. You can view the")
        p_warning("exact data that will be sent.")

        while True:
            print()
            p_question("Report your install?")
            act = self.choice("Choice (y/n/d)", {
                "y": "Yes",
                "n": "No",
                "d": "View the data that will be sent",
            }, default=None)

            if act == "n":
                return
            elif act == "d":
                self.show_report_data(data)
                continue
            elif act == "y":
                break
            else:
                assert False

        if reporting.send_report(url, data):
            p_success("Your install has been counted. Thank you! ❤")
        else:
            p_warning("Failed to send report! No worries.")

        print()
        print()
        time.sleep(1)

    def report(self):
        config = reporting.get_report_config()
        if config is None:
            return

        try:
            self.report_inner(*config)
        except Exception:
            logging.exception("Reporting failed, continuing...")

    def step2_completed(self, report=False):
        self.install_info(report)

        print()
        time.sleep(2)
        p_prompt( "Press enter to reboot the system.")
        self.input()
        time.sleep(1)
        self.reboot()

    def step2_indirect(self, report=False):
        self.hide_new_volume()

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
        p_message( "1. Wait 25 seconds for the system to fully shut down.")
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
        p_message(f"7. Once the '{DISTRO} installer' screen appears, follow the prompts.")
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
        self.shutdown()

    def action_resize(self, resizable):
        choices = {str(i): p.desc for i,p in enumerate(self.partitions) if p in resizable}

        print()
        if len(resizable) > 1 or self.expert:
            p_question("Choose an existing partition to resize:")
            idx = self.choice("Partition", choices)
            target = self.partitions[int(idx)]
        else:
            target = resizable[0]

        info = self.get_resize_info(target)

        p_message( "We're going to resize this partition:")
        p_message(f"  {target.desc}")
        p_info(   f"  Total size: {col()}{ssize(info.total)}")
        p_info(   f"  Free space: {col()}{ssize(info.free)}")
        p_info(   f"  Available space: {col()}{ssize(info.avail)}")
        p_info(   f"  Overhead: {col()}{ssize(info.overhead)}")
        p_info(   f"  Minimum new size: {col()}{ssize(info.min_size)} ({info.min_perc:.2f}%)")
        print()
        if info.has_large_overhead:
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

            if not info.can_shrink:
                p_error("  Not enough available space to resize. Please follow the instructions")
                p_error("  above to continue.")
                return False

            if not self.yesno("Continue anyway?"):
                return False
            print()

        if not info.can_shrink:
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
        if info.total / 2 < info.min_size:
            default = "min"
        while True:
            val = self.get_size("New size", default=default, min=info.min_size, total=info.total)
            if val is None:
                continue
            try:
                val = self.check_resize_size(info, val)
            except SizeTooSmallError as e:
                p_error(f"Size is too small, please enter a value > {ssize(e.limit)} ({info.min_perc:.2f}%)")
                continue
            except SizeTooLargeError as e:
                p_error(f"Size is too large, please enter a value < {ssize(e.limit)}")
                continue
            freeing = info.total - val
            print()
            p_message(f"Resizing will free up {ssize(freeing)} of space.")
            if not info.frees_enough_for_install(val):
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
            self.resize_partition(target, val)
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
            self.select_disk()
        else:
            self.select_disk(self.external_disks[idx - 2]["DeviceIdentifier"])

        return True

    def show_system_info(self):
        p_info(f"  Product name: {col()}{self.sysinfo.product_name}")
        p_info(f"  SoC: {col()}{self.sysinfo.soc_name}")
        p_info(f"  Device class: {col()}{self.sysinfo.device_class}")
        p_info(f"  Product type: {col()}{self.sysinfo.product_type}")
        p_info(f"  Board ID: {col()}{self.sysinfo.board_id:#x}")
        p_info(f"  Chip ID: {col()}{self.sysinfo.chip_id:#x}")
        p_info(f"  System firmware: {col()}{self.sysinfo.sys_firmware}")
        p_info(f"  Boot UUID: {col()}{self.sysinfo.boot_uuid}")
        p_info(f"  Boot VGID: {col()}{self.sysinfo.boot_vgid}")
        p_info(f"  Default boot VGID: {col()}{self.sysinfo.default_boot}")
        p_info(f"  Boot mode: {col()}{self.sysinfo.boot_mode}")
        p_info(f"  OS version: {col()}{self.sysinfo.macos_ver} ({self.sysinfo.macos_build})")
        p_info(f"  OS restore version: {col()}{self.sysinfo.macos_restore_ver}")
        p_info(f"  Main firmware version: {col()}{self.sysinfo.sfr_ver} ({self.sysinfo.sfr_build})")
        if self.sysinfo.fsfr_ver:
            p_info(f"  Fallback firmware version: {col()}{self.sysinfo.fsfr_ver} ({self.sysinfo.fsfr_build})")
        else:
            p_info(f"  No Fallback System Firmware / rOS")
        p_info(f"  SFR version: {col()}{self.sysinfo.sfr_full_ver}")
        p_info(f"  SystemRecovery version: {col()}{self.sysinfo.sros_full_ver} ({self.sysinfo.sros_ver} {self.sysinfo.sros_build})")
        p_info(f"  Login user: {col()}{self.sysinfo.login_user}")

    def main(self):
        print()
        p_message(f"Welcome to the {DISTRO} installer!")
        print()
        p_message("This installer will guide you through the process of setting up")
        p_message(f"{DISTRO} on your Mac.")
        print()
        p_message("Please make sure you are familiar with our documentation at:")
        p_plain( f"  {col(BLUE, BRIGHT)}{DISTRO_DOCS}{col()}")
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
        self.collect_system_info()
        self.show_system_info()

        print()

        try:
            self.check_system()
        except BuggyMacOSError:
            p_error("Dangerously buggy macOS version detected!")
            print()
            p_warning("You have a machine with a ProMotion display, and you are running macOS")
            p_warning("Sonoma earlier than 14.2 or your System Firmware is in this range. Due to")
            p_warning("critical macOS bugs, this combination can lead to an unbootable system under")
            p_warning("certain conditions.")
            print()
            p_message("Please upgrade your system to macOS 14.2 or later and run this installer")
            p_message("again to continue. This version resolves the bug and will make your machine")
            p_message("safe again. If you have multiple macOS installs, we recommend not booting")
            p_message("macOS Sonoma versions prior to 14.2 on this machine.")
            print()
            sys.exit(1)
        except UnsupportedDeviceError:
            p_error("This device is not supported yet!")
            p_error("Please check out the Asahi Linux Blog for updates on device support:")
            print()
            p_error("   https://asahilinux.org/blog/")
            print()
            sys.exit(1)
        except NoLoginUserError:
            p_error("Could not detect logged in user.")
            p_error("Perhaps you are running this installer over SSH?")
            p_error("Please make sure a user is logged into the local console.")
            p_error("You can use SSH as long as there is a local login session.")
            sys.exit(1)
        except MacOSTooOldError as e:
            p_error("Your macOS version is too old.")
            p_error(f"Please upgrade to macOS {e.min_version} or newer.")
            sys.exit(1)

        while self.main_loop():
            pass

    def main_loop(self):
        p_progress("Collecting partition information...")

        self.disk_info_init()

        if self.sys_disk:
            p_info(f"  System disk: {col()}{self.sys_disk}")

        if self.external_disks:
            p_info(f"  Found {len(self.external_disks)} external disk(s)")

        print()

        p_progress("Collecting OS information...")
        self.collect_os_info()
        if self.is_edu_128gb:
            p_warning("Education-only 128GB device detected, allowing to resize macOS below safe limits")
            p_warning("System updates may fail if less than ~30GB of free space remains on the main partition")

        print()
        if self.cur_disk == self.sys_disk:
            t = "system"
        else:
            t = "external"
        p_message(f"Partitions in {t} disk ({self.cur_disk}):")

        r = col(YELLOW) + "R" + col()
        b = col(GREEN) + "B" + col()
        u = col(RED) + "?" + col()
        d = col(BRIGHT) + "*" + col()
        marks = {BOOT_RECOVERY: r, BOOT_BOOTED: b, BOOT_UNKNOWN: u}

        for i, p in enumerate(self.partitions):
            if p.desc is None:
                continue
            p_choice(f"  {col(BRIGHT)}{i}{col()}: {p.desc}")
            if not p.os:
                continue
            for os in p.os:
                if not os.version:
                    continue
                state = marks.get(self.os_boot_state(os), " ")
                state += d if self.sysinfo.default_boot == os.vgid else " "
                p_plain(f"    OS: [{state}] {describe_os(os)}")
                if os.attached_partitions:
                    p_plain(f"      Extra partitions: {' '.join('#' + str(i.index) for i in os.attached_partitions)}")

        print()
        p_plain(f"  [{b} ] = Booted OS, [{r} ] = Booted recovery, [{u} ] = Unknown")
        p_plain(f"  [ {d}] = Default boot volume")
        print()

        self.check_cur_os()

        available = self.available_actions()
        if not available:
            p_error("No actions available on this system.")
            p_message("No partitions have enough free space to be resized, and there is")
            p_message("nothing else to be done.")
            sys.exit(1)

        actions = {self.ACTION_KEYS[a]: self.ACTION_LABELS[a] for a in available}
        # Never make wipe the default!
        default = next((self.ACTION_KEYS[a] for a in available if a != ACTION_WIPE), None)

        actions["q"] = "Quit without doing anything"
        default = default or "q"

        print()
        p_question("Choose what to do:")
        act = self.choice("Action", actions, default)

        if act == "f":
            return self.action_install_into_free()
        elif act == "a":
            return self.action_install_into_container(self.partitions_empty_apfs)
        elif act == "r":
            return self.action_resize(self.partitions_resizable)
        elif act == "m":
            return self.action_repair_or_upgrade(self.partitions_upgradeable, upgrade=True)
        elif act == "p":
            return self.action_repair_or_upgrade(self.partitions_incomplete, upgrade=False)
        elif act == "d":
            return self.action_select_disk()
        elif act == "w":
            return self.action_wipe()
        elif act == "v":
            return self.action_rebuild_vendorfw(self.partitions_vendorfw)
        elif act == "7":
            return self.action_set_vol_bootable(self.partitions_no_volboot)
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
    console.addFilter(lambda record: record.name != user_log.name)
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
        InstallerCLI(installer_version).main()
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
