# SPDX-License-Identifier: MIT
import os, os.path, plistlib, subprocess, logging
from dataclasses import dataclass

import m1n1
from util import *

UUID_SROS = "3D3287DE-280D-4619-AAAB-D97469CA9C71"
UUID_FROS = "C8858560-55AC-400F-BBB9-C9220A8DAC0D"

@dataclass
class OSInfo:
    partition: object
    vgid: str
    label: str = None
    sys_volume: str = None
    data_volume: str = None
    stub: bool = False
    version: str = None
    m1n1_ver: str = None
    system: object = None
    data: object = None
    preboot: object = None
    recovery: object = None
    rec_vgid: str = None
    preboot_vgid: str = None
    bp: object = None
    paired: bool = False
    admin_users: object = None

    def __str__(self):
        if self.vgid == UUID_SROS:
            return f"recoveryOS v{self.version} [Primary recoveryOS]"
        elif self.vgid == UUID_FROS:
            return f"recoveryOS v{self.version} [Fallback recoveryOS]"

        lbl = col(BRIGHT) + self.label + col()
        if not self.stub:
            macos = f"{col(BRIGHT, GREEN)}macOS v{self.version}{col()}"
            if self.m1n1_ver is not None:
                return f"[{lbl}] {macos} + {col(CYAN)}m1n1 {self.m1n1_ver}{col()} [{self.sys_volume}, {self.vgid}]"
            elif self.bp and self.bp.get("coih", None):
                return f"[{lbl}] {macos} + {col(YELLOW)}unknown fuOS{col()} [{self.sys_volume}, {self.vgid}]"
            else:
                return f"[{lbl}] {macos} [{self.sys_volume}, {self.vgid}]"
        elif self.bp and self.bp.get("coih", None):
            if self.m1n1_ver:
                return f"[{lbl}] {col(BRIGHT, CYAN)}m1n1 {self.m1n1_ver}{col()} (macOS {self.version} stub) [{self.sys_volume}, {self.vgid}]"
            else:
                return f"[{lbl}] {col(BRIGHT, YELLOW)}unknown fuOS{col()} (macOS {self.version} stub) [{self.sys_volume}, {self.vgid}]"
        else:
            return f"[{lbl}] {col(BRIGHT, RED)}incomplete install{col()} (macOS {self.version} stub) [{self.sys_volume}, {self.vgid}]"

class OSEnum:
    def __init__(self, sysinfo, dutil, sysdsk):
        self.sysinfo = sysinfo
        self.dutil = dutil
        self.sysdsk = sysdsk

    def collect(self, parts):
        logging.info("OSEnum.collect()")
        for p in parts:
            p.os = []
            if p.type == "Apple_APFS_Recovery":
                self.collect_recovery(p)
            else:
                self.collect_part(p)

    def collect_recovery(self, part):
        logging.info(f"OSEnum.collect_recovery(part={part.name})")
        if part.container is None:
            return

        recs = []

        for volume in part.container["Volumes"]:
            if volume["Roles"] == ["Recovery"]:
                recs.append(volume)

        if len(recs) != 1:
            return

        os = OSInfo(partition=part, vgid=UUID_SROS,
                    rec_vgid=recs[0]["APFSVolumeUUID"],
                    version=self.sysinfo.sfr_ver)
        logging.info(f" Found SROS: {os}")
        part.os.append(os)
        if self.sysinfo.fsfr_ver:
            os = OSInfo(partition=part, vgid=UUID_FROS,
                        version=self.sysinfo.fsfr_ver)
            logging.info(f" Found FROS: {os}")
            part.os.append(os)

    def collect_part(self, part):
        logging.info(f"OSEnum.collect_part(part={part.name})")
        if part.container is None:
            return

        part.os = []

        ct = part.container
        ct_name = ct.get("ContainerReference", None)

        by_role = {}
        by_device = {}

        for volume in ct["Volumes"]:
            by_role.setdefault(tuple(volume["Roles"]), []).append(volume)
            by_device[volume["DeviceIdentifier"]] = volume

        volumes = {}

        for role in ("Preboot", "Recovery"):
            vols = by_role.get((role,), None)
            if not vols:
                logging.info(f" No {role} volume")
                return
            elif len(vols) > 1:
                logging.info(f"  Multiple {role} volumes ({vols})")
                return
            volumes[role] = vols[0]

        for vg in ct["VolumeGroups"]:
            data = [i for i in vg["Volumes"] if i["Role"] == "Data"]
            system = [i for i in vg["Volumes"] if i["Role"] == "System"]
            if len(data) != 1 or len(system) != 1:
                logging.info(f"  Weird VG: {vg['Volumes']}")
                continue
            data = data[0]["DeviceIdentifier"]
            system = system[0]["DeviceIdentifier"]

            volumes["Data"] = by_device[data]
            volumes["System"] = by_device[system]

            vgid = vg["APFSVolumeGroupUUID"]

            if self.sysinfo.boot_uuid == vgid:
                for volume in self.dutil.disk_parts[ct_name]["APFSVolumes"]:
                    if "MountedSnapshots" not in volume:
                        continue
                    snapshots = volume["MountedSnapshots"]
                    if volume["DeviceIdentifier"] == system and len(snapshots) == 1:
                        volumes = dict(volumes)
                        volumes["System"]["DeviceIdentifier"] = snapshots[0]["SnapshotBSD"]

            os = self.collect_os(part, volumes, vgid)
            logging.info(f" Found {os}")
            part.os.append(os)

        return part.os

    def collect_os(self, part, volumes, vgid):
        logging.info(f"OSEnum.collect_os(part={part.name}, vgid={vgid})")
        mounts = {}

        for role in ("Preboot", "Recovery", "System"):
            mounts[role] = self.dutil.mount(volumes[role]["DeviceIdentifier"])
            logging.info(f"  mounts[{role}]: {mounts[role]}")

        # Data will fail to mount for FileVault-enabled OSes; ignore that.
        try:
            mounts["Data"] = self.dutil.mount(volumes["Data"]["DeviceIdentifier"])
            logging.info(f"  mounts[Data]: {mounts['Data']}")
        except:
            mounts["Data"] = None
            logging.info(f"  Failed to mount Data (FileVault?)")

        rec_vgid = volumes["Recovery"]["APFSVolumeUUID"]
        preboot_vgid = volumes["Preboot"]["APFSVolumeUUID"]

        stub = not os.path.exists(os.path.join(mounts["System"], "Library"))

        sys_volume = volumes["System"]["DeviceIdentifier"]
        data_volume = volumes["Data"]["DeviceIdentifier"]
        label = volumes["System"]["Name"]

        osi = OSInfo(partition=part, vgid=vgid, stub=stub, label=label,
                     sys_volume=sys_volume,
                     data_volume=data_volume,
                     system=mounts["System"],
                     data=mounts["Data"],
                     preboot=mounts["Preboot"],
                     recovery=mounts["Recovery"],
                     rec_vgid=rec_vgid,
                     preboot_vgid=preboot_vgid)

        for name in ("SystemVersion.plist", "SystemVersion-disabled.plist"):
            try:
                logging.info(f"  Trying {name}...")
                sysver = plistlib.load(open(os.path.join(mounts["System"],
                    "System/Library/CoreServices", name), "rb"))
                osi.version = sysver["ProductVersion"]
                logging.info(f"    Version: {osi.version}")
                break
            except FileNotFoundError:
                logging.info(f"    Not Found")
                continue

        try:
            auri = plistlib.load(open(os.path.join(mounts["Preboot"], vgid,
                                                   "var/db/AdminUserRecoveryInfo.plist"), "rb"))
            osi.admin_users = list(auri.keys())
            logging.info(f"  Admin users: {osi.admin_users}")
        except:
            logging.warning(f"  Failed to get AdminUserRecoveryInfo.plist")
            pass

        try:
            bps = self.bputil("-d", "-v", vgid)
        except subprocess.CalledProcessError:
            logging.warning(f"  bputil failed")
            return osi

        osi.bp = {}
        for k in ("coih", "nsih"):
            tag = f"({k}): ".encode("ascii")
            if tag in bps:
                val = bps.split(tag)[1].split(b"\n")[0].decode("ascii")
                if val == "absent":
                    val = None
                osi.bp[k] = val
                logging.info(f"  BootPolicy[{k}] = {val}")

        if coih := osi.bp.get("coih", None):
            fuos_path = os.path.join(mounts["Preboot"], vgid, "boot",
                                     osi.bp["nsih"],
                                     "System/Library/Caches/com.apple.kernelcaches",
                                     "kernelcache.custom." + coih)
            if os.path.exists(fuos_path):
                osi.m1n1_ver = m1n1.get_version(fuos_path)
                if osi.m1n1_ver:
                    logging.info(f"  m1n1 version found: {osi.m1n1_ver}")

        if b": Paired" in bps:
            osi.paired = True

        return osi

    def bputil(self, *args):
        result = subprocess.run(["bputil"] + list(args),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        return result.stdout
