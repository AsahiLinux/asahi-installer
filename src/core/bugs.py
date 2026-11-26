# SPDX-License-Identifier: GPL-2.0-or-later
import subprocess, json, datetime, logging, sys

from .util import *

BUGGY_SFR_MIN = "14.0"

SAFE_MACOS_RVERSION_MIN = "23.3.55.5.2" # 14.2 beta 4
SAFE_MACOS_VERSION_MIN = "14.3"
# Allow the recoveryOS we use
ALLOWED_RECOVERYOS_VERSIONS = ("13.5",)

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

def is_bugged(si):
    if si.device_class not in PROMOTION_DEVICES:
        logging.info("bugs: Not a ProMotion device")
        return False

    if split_ver(si.sfr_ver) < split_ver(BUGGY_SFR_MIN):
        logging.info("bugs: SFR not updated beyond problem version")
        return False

    if si.macos_restore_ver and split_ver(si.macos_restore_ver) >= split_ver(SAFE_MACOS_RVERSION_MIN):
        logging.info("bugs: macOS is new enough to guarantee safety")
        return False

    if si.macos_ver and split_ver(si.macos_ver) >= split_ver(SAFE_MACOS_VERSION_MIN):
        logging.info("bugs: macOS is new enough to guarantee safety")
        return False

    if "recovery" in si.boot_mode and si.macos_ver in ALLOWED_RECOVERYOS_VERSIONS:
        logging.info("bugs: allowlisted recoveryOS, assuming we're OK")
        return False

    return True
