# SPDX-License-Identifier: MIT
import os, os.path, plistlib, subprocess
from dataclasses import dataclass

@dataclass
class OSInfo:
    partition: str
    vgid: str
    stub: bool = False
    version: str = None
    m1n1_ver: str = None
    system: object = None
    data: object = None
    preboot: object = None
    recovery: object = None
    rec_vgid: str = None
    bp: object = None

    def __str__(self):
        if not self.stub:
            if self.m1n1_ver is not None:
                return f"macOS v{self.version} + m1n1 {self.m1n1_ver} [{self.vgid}]"
            elif self.bp and self.bp.get("coih", None):
                return f"macOS v{self.version} + unknown fuOS [{self.vgid}]"
            else:
                return f"macOS v{self.version} [{self.vgid}]"
        elif self.bp and self.bp.get("coih", None):
            if self.m1n1_ver:
                return f"m1n1 v{self.m1n1_ver} (macOS {self.version} stub) [{self.vgid}]"
            else:
                return f"unknown fuOS (macOS {self.version} stub) [{self.vgid}]"
        else:
            return f"broken stub (macOS {self.version} stub) [{self.vgid}]"

class OSEnum:
    def __init__(self, sysinfo, dutil, sysdsk):
        self.sysinfo = sysinfo
        self.dutil = dutil
        self.sysdsk = sysdsk
    
    def collect(self, parts):
        for p in parts:
            self.collect_one(p)

    def collect_one(self, part):
        if part.container is None:
            return

        ct = part.container
        by_role = {}

        for volume in ct["Volumes"]:
            by_role.setdefault(tuple(volume["Roles"]), []).append(volume)

        for role in ("Preboot", "Recovery", "Data", "System"):
            vols = by_role.get((role,), None)
            if not vols:
                return
            elif len(vols) > 1:
                return

        mounts = {}

        for role in ("Preboot", "Recovery", "Data", "System"):
            mounts[role] = self.dutil.mount(by_role[(role,)][0]["DeviceIdentifier"])

        vgid = by_role[("Data",)][0]["APFSVolumeUUID"]
        rec_vgid = by_role[("Recovery",)][0]["APFSVolumeUUID"]

        stub = not os.path.exists(os.path.join(mounts["System"], "Library"))

        osi = OSInfo(partition=part, vgid=vgid, stub=stub,
                     system=mounts["System"],
                     data=mounts["Data"],
                     preboot=mounts["Preboot"],
                     recovery=mounts["Recovery"],
                     rec_vgid=rec_vgid)

        try:
            sysver = plistlib.load(open(os.path.join(mounts["System"],
                "System/Library/CoreServices/SystemVersion.plist"), "rb"))
            osi.version = sysver["ProductVersion"]
        except FileNotFoundError:
            pass

        part.os = osi

        try:
            bps = self.bputil("-d", "-v", vgid)
        except subprocess.CalledProcessError:
            return osi

        osi.bp = {}
        for k in ("coih", "nsih"):
            tag = f"({k}): ".encode("ascii")
            if tag in bps:
                val = bps.split(tag)[1].split(b"\n")[0].decode("ascii")
                if val == "absent":
                    val = None
                osi.bp[k] = val

        if coih := osi.bp.get("coih", None):
            fuos_path = os.path.join(mounts["Preboot"], vgid, "boot",
                                     osi.bp["nsih"],
                                     "System/Library/Caches/com.apple.kernelcaches",
                                     "kernelcache.custom." + coih)
            fuos = open(fuos_path, "rb").read()
            if b"##m1n1_ver##" in fuos:
                osi.m1n1_ver = fuos.split(b"##m1n1_ver##")[1].split(b"\0")[0].decode("ascii")

        return osi

    def bputil(self, *args):
        result = subprocess.run(["bputil"] + list(args),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        return result.stdout
