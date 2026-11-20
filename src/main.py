#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
import os, shlex, subprocess

from terminal import *
from gui import InstallerGUI
from cli import InstallerCLI

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
    for var in ("INSTALLER_BASE", "INSTALLER_DATA", "REPO_BASE", "IPSW_BASE", "EXPERT", "REPORT", "REPORT_TAG", "ASAHI_GRAPHICAL"):
        logging.info(f"  {var}={os.environ.get(var, None)}")

    try:
        installer_version = open("version.tag", "r").read().strip()
        logging.info(f"Version: {installer_version}")
        if os.environ.get("ASAHI_GRAPHICAL") == "1":
            InstallerGUI(installer_version).main()
        else:
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
