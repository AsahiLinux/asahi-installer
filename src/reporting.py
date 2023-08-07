import json, os, logging, time
from urllib import request, parse
from util import *

EXPLANATIONS = {
    "device_class":
        "# The model code of your device. For example, j274ap means\n"
        "# 'Mac mini (M1, 2020)'.",
    "chip_id":
        "# The kind of chip your device has. For example, 0x8103 means Apple M1.\n"
        "# This is redundant (it is the same for any given device_class), but it\n"
        "# makes grouping reports by chips instead of devices a bit easier.",
    "macos_ver":
        "# The macOS version you are installing from. This helps us know how up\n"
        "# to date people are, so we can decide when to start requiring a newer\n"
        "# version. The text in parentheses is the build ID, which is the same\n"
        "# for any given release version of macOS (but varies for betas).",
    "sfr_ver":
        "# Your System Firmware version. This is usually the same as the macOS\n"
        "# version, unless you have multiple macOS installs.",
    "boot_mode":
        "# Whether you are installing from macOS or recoveryOS.",
    "os_name":
        "# The OS you selected to install. This lets us know what the most\n"
        "# popular OS choices are.",
    "os_package":
        "# The OS package filename. This tells us the particular OS version that\n"
        "# was installed.",
    "os_firmware":
        "# The firmware version used for this specific OS install. This is\n"
        "# one of a few specific options, since our kernels must support all\n"
        "# firmware versions used in the wild.",
    "disk_size":
        "# The SSD size of your machine, in gigabytes. This helps us gauge how\n"
        "# painful having to keep a macOS install around is for our users.",
    "disk_fraction":
        "# The fraction of your disk you allocated to your install, rounded to\n"
        "# 5%. This helps us understand how many people are using Asahi as\n"
        "# their primary OS, secondary OS, or just trying it out.",
    "installer":
        "# Version and configuration information for the installer. This lets us\n"
        "# know whether you used the official installer or something else.\n"
        "# The information is the same for everyone who installs using the same\n"
        "# command line.",
}

def show_data(data):
    print()
    p_message(f"This is the data that will be sent:")

    for line in json.dumps(data, indent=4).split("\n"):
        if not line:
            continue
        for key, exp in EXPLANATIONS.items():
            indent = line[:len(line) - len(line.lstrip())]
            if line.strip().startswith(f'"{key}"'):
                exp = indent + exp.replace("\n", "\n" + indent)
                p_message(exp)
                break
        p_info(line)
    print()

def report_inner(m, url, tag):
    disk_size = m.dutil.get_disk_size(m.cur_disk)
    size = round(20 * m.osins.install_size / disk_size) / 20

    data = {
        "device_class": m.sysinfo.device_class,
        "chip_id": f"{m.sysinfo.chip_id:#x}",
        "macos_ver": f"{m.sysinfo.macos_ver} ({m.sysinfo.macos_build})",
        "sfr_ver": f"{m.sysinfo.sfr_ver} ({m.sysinfo.sfr_build})",
        "boot_mode": m.sysinfo.boot_mode,
        "os_name": m.osins.template["name"],
        "os_package": m.osins.template.get("package", None),
        "os_firmware": m.ipsw.version,
        "disk_size": round(disk_size / 1000_000_000),
        "disk_fraction": size,
        "installer": {
            "tag": tag,
            "version": m.version,
            "env": {},
        },
    }

    for var in ("INSTALLER_BASE", "INSTALLER_DATA", "REPO_BASE"):
        data["installer"]["env"][var] = os.environ.get(var, None)

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
        act = m.choice("Choice (y/n/d)", {
            "y": "Yes",
            "n": "No",
            "d": "View the data that will be sent",
        }, default=None)

        if act == "n":
            return
        elif act == "d":
            show_data(data)
            continue
        elif act == "y":
            break
        else:
            assert False

    logging.info(f"Report data: {data!r}")

    try:
        headers = {"Content-Type": "application­/json"}
        postdata = json.dumps(data).encode("utf-8")
        req = request.Request(url, data=postdata, method="POST", headers=headers)
        with request.urlopen(req) as fd:
            fd.read()
            if fd.status == 200:
                p_success("Your install has been counted. Thank you! ❤")
            else:
                p_warning("Failed to send report! No worries.")

    except Exception as e:
        p_warning("Failed to send report! No worries.")

    print()
    print()
    time.sleep(1)

def report(m):
    url = os.environ.get("REPORT", None)
    tag = os.environ.get("REPORT_TAG", None)

    if not tag or not url:
        return

    try:
        report_inner(m, url, tag)
    except Exception as e:
        logging.exception("Reporting failed, continuing...")
