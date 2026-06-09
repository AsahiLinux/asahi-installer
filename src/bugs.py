# SPDX-License-Identifier: MIT
import subprocess, json, datetime, logging, sys
from util import *

BUGGY_SFR_MIN = "14.0"

SAFE_MACOS_RVERSION_MIN = "23.3.55.5.2" # 14.2 beta 4
SAFE_MACOS_VERSION_MIN = "14.3"
# Allow the recoveryOS we use
ALLOWED_RECOVERYOS_VERSIONS = ("13.5",)

GGATE_VALIDATION_MIN = "27.0"

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

def run_checks_ggate_validation(main):
    if main.sysinfo.macos_ver and split_ver(main.sysinfo.macos_ver) < split_ver(GGATE_VALIDATION_MIN):
        logging.info("bugs: Tahoe or lower")
        return
    p_error("macOS Golden Gate detected!")
    print()
    p_warning("Apple has changed how the boot picker and Startup Disk applications detect")
    p_warning('"valid" macOS installs. When using either from macOS 27, your Asahi partition')
    p_warning("will not be visible! We believe this to be a bug, and have filed a report.")
    print()
    p_message("If you are running the installer because you have noticed that your Asahi partition")
    p_message("has disappeared, do not stress. Your Asahi partition is still there, and you have")
    p_message("not lost any data. The Apple Silicon boot picker is a macOS application running")
    p_message("in the default boot volume's recovery environment and therefore still works if")
    p_message("your default boot disk is macOS 26 and below or Asahi.")
    print()
    p_message("If you have a secondary installation of macOS 26 or below, set this as your default")
    p_message("Startup Disk to restore access to Asahi. If this is your only install, it is possible")
    p_message("that the Fallback recoveryOS is still using macOS 26 or older, and in that case you can")
    p_message("enter it by turning off the machine, rapidly pressing and releasing the power button, then")
    p_message('holding it until the "Loading startup options..." message appears')
    print()
    exit(1)

def run_checks_promotion(main):
    if main.sysinfo.device_class not in PROMOTION_DEVICES:
        logging.info("bugs: Not a ProMotion device")
        return

    if split_ver(main.sysinfo.sfr_ver) < split_ver(BUGGY_SFR_MIN):
        logging.info("bugs: SFR not updated beyond problem version")
        return

    if main.sysinfo.macos_restore_ver and split_ver(main.sysinfo.macos_restore_ver) >= split_ver(SAFE_MACOS_RVERSION_MIN):
        logging.info("bugs: macOS is new enough to guarantee safety")
        return

    if main.sysinfo.macos_ver and split_ver(main.sysinfo.macos_ver) >= split_ver(SAFE_MACOS_VERSION_MIN):
        logging.info("bugs: macOS is new enough to guarantee safety")
        return

    if "recovery" in main.sysinfo.boot_mode and main.sysinfo.macos_ver in ALLOWED_RECOVERYOS_VERSIONS:
        logging.info("bugs: allowlisted recoveryOS, assuming we're OK")
        return

    request_upgrade()
    sys.exit(1)

def run_checks(main):
    run_checks_ggate_validation(main)
    run_checks_promotion(main)
