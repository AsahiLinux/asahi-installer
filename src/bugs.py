# SPDX-License-Identifier: MIT
import subprocess, json, datetime, logging, sys
from util import *

BUGGY_SFR_MIN = "14.0"

ALLOWED_MACOS_MIN = "14.1.1"

PROMOTION_DEVICES = {
    "j314cap",
    "j314sap",
    "j316cap",
    "j316sap",
    "j414cap",
    "j414sap",
    "j416cap",
    "j416sap",
    "j514cap",
    "j514sap",
    "j516cap",
    "j516sap",
}

def get_boottime():
    p = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, check=True)
    ts = int(p.stdout.split(b"sec = ")[1].split(b",")[0])
    dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    logging.info(f"System boot time: {dt}")
    return dt

def get_logs(start, process):
    logging.info(f"Getting {process} system logs")
    start_ts = int(start.timestamp())
    p = subprocess.run(["log", "show", "-p", process,
                        "--start", f"@{start_ts}", "--style", "json",
                        "--timezone", "utc"],
                       capture_output=True, check=True)
    for entry in json.loads(p.stdout):
        ts = entry["timestamp"].replace("+0000", "+00:00")
        dt = datetime.datetime.fromisoformat(ts)
        yield (dt, entry["eventMessage"])

def get_startup_display_mode():
    logging.info("get_startup_display_mode()")
    boot_time = get_boottime()
    startup = False
    for ts, message in get_logs(boot_time, "WindowServer"):
        logging.info(f"Log: {ts} {message}")
        delta = ts - boot_time
        if delta > datetime.timedelta(seconds=10):
            logging.warning("Failed to find startup/mode logs for WindowServer")
            break
        if "Server is starting up" in message:
            assert not startup
            startup = True
        if startup and "Display 1 current mode" in message:
            mode = int(message.split("[")[1].split(" ")[0])
            logging.info(f"Internal panel boot mode: {mode}")
            return mode

    return None

def request_upgrade():
    p_error("Mismatched System Firmware / System Recovery detected!")
    print()
    p_warning("You have a machine with a ProMotion display, with a System Firmware version")
    p_warning("newer than 14.0 and a System Recovery version older than 14.0. Due to a")
    p_warning("critical macOS bug, this combination can lead to an unbootable system under")
    p_warning("certain conditions.")
    print()
    p_plain("Your machine is not currently in imminent danger, but will be safer if you")
    p_plain("upgrade to macOS Sonoma 14.1.1 or later. With this version, Apple added a")
    p_plain("temporary workaround that will make it harder to hit the bug in practice.")
    print()
    p_message("Please upgrade your system to macOS 14.1.1 or later and run this installer")
    p_message("again to continue. Do NOT change your display configuration until the upgrade")
    p_message("is complete.")
    print()

def sadness(sysinfo):
    p_error("Your machine is affected by a critical macOS bug!")
    print()
    p_warning("You have a machine with a ProMotion display, with a System Firmware version")
    p_warning("newer than 14.0 and a System Recovery version older than 14.0. Due to a")
    p_warning("critical Apple bug, this combination can lead to an unbootable system under")
    p_warning("certain conditions.")
    print()
    if split_ver(sysinfo.sros_ver) < split_ver(BUGGY_SFR_MIN):
        p_error("We have determined that your machine is affected and currently has an")
        p_error("inoperable System Recovery. This is a dangerous condition that can make it")
        p_error("impossible to recover from certain situations. Installing Asahi Linux is also")
        p_error("not possible in this state.")
    else:
        p_error("We have determined that your machine is affected and would not be able to")
        p_error("successfully complete an Asahi Linux installation, as it cannot boot older")
        p_error("versions of macOS Recovery in this state.")
    print()
    p_error("We cannot continue with the install. Sorry. You will have to wait for Apple")
    p_error("to fix this properly in a future update. This bug is entirely outside of our")
    p_error("control and there is no easy workaround at this time.")
    print()
    p_plain("More information:")
    print()
    p_plain( f"    {col(BLUE, BRIGHT)}https://github.com/AsahiLinux/docs/wiki/macOS-Sonoma-Boot-Failures{col()}")

def you_are_safe(main):
    p_plain("Good news! Your machine should be unaffected by the critical ProMotion")
    p_plain("boot failure bug at this time. If you have any other versions of macOS")
    p_plain("installed side-by-side, we strongly recommend not booting them until")
    p_plain("Apple properly and fully fixes this bug, as that could cause the issue")
    p_plain("to trigger and your machine to become unbootable. Asahi Linux installs")
    p_plain("are safe and will not cause any danger to your system.")
    print()
    p_message("Press enter to continue.")
    main.input()

def run_checks(main):
    if main.sysinfo.device_class not in PROMOTION_DEVICES:
        return

    if split_ver(main.sysinfo.sfr_ver) < split_ver(BUGGY_SFR_MIN):
        return

    p_progress("Checking whether your machine is affected by critical Apple bugs...")
    print()

    hz = main.sysinfo.get_refresh_rate()
    if hz is None:
        p_warning("Could not check ProMotion display status")
        p_plain("This probably means your laptop lid is closed. Please open it and try again.")
        p_plain("(You're going to have to use the power button soon anyway!)")
        print()
        sys.exit(1)

    p_info(f"  Current display refresh rate: {col()}{hz} Hz")
    print()
    if hz != 120.0:
        p_error("Your display is not set to ProMotion mode (120 Hz). Please change your")
        p_error("display refresh rate to ProMotion mode in System Settings, then reboot")
        p_error("your machine with the lid open and try again.")
        print()
        p_error("Due to a critical Apple bug, it is not safe to install multiple operating")
        p_error("systems on your Mac with a non-ProMotion refresh rate configured.")
        print()
        sys.exit(1)

    mode = get_startup_display_mode()
    if mode is None:
        p_warning("Could not check boot-time display configuration")
        p_plain("This can happen if you have not rebooted your machine in several days.")
        p_plain("Please reboot your machine with the laptop lid open, then try again.")
        print()
        sys.exit(1)

    if split_ver(main.sysinfo.macos_ver) < split_ver(ALLOWED_MACOS_MIN):
        if mode != 2:
            p_warning("Mismatch between screen boot mode and current screen mode detected.")
            print()
            p_plain("Please reboot your machine and try again.")
            print()
        else:
            request_upgrade()
        sys.exit(1)

    if mode == 2:
        you_are_safe(main)
    else:
        sadness(main.sysinfo)
        sys.exit(1)
