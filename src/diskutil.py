# SPDX-License-Identifier: MIT
import plistlib, subprocess, sys
from dataclasses import dataclass

@dataclass
class Partition:
    name: str
    offset: int
    size: int
    free: bool
    type: str
    desc: str = None
    label: str = None
    info: object = None
    container: object = None
    os: object = None

class DiskUtil:
    FREE_THRESHOLD = 16 * 1024 * 1024
    def __init__(self):
        self.verbose = "-v" in sys.argv
    
    def action(self, *args, verbose=False):
        if verbose and self.verbose:
            print(" + diskutil " + " ".join(args))
        subprocess.run(["diskutil"] + list(args), check=True, capture_output=(not self.verbose))

    def get(self, *args):
        result = subprocess.run(["diskutil"] + list(args),
                                stdout=subprocess.PIPE, check=True)
        return plistlib.loads(result.stdout)

    def get_list(self):
        self.list = self.get("list", "-plist")
        self.disk_list = self.list["WholeDisks"]
        self.disk_parts = {dsk["DeviceIdentifier"]: dsk for dsk in self.list["AllDisksAndPartitions"]}

    def get_apfs_list(self, dev=None):
        if dev:
            apfs = self.get("apfs", "list", dev, "-plist")
        else:
            apfs = self.get("apfs", "list", "-plist")
        for ctnr in apfs["Containers"]:
            self.ctnr_by_ref[ctnr["ContainerReference"]] = ctnr
            self.ctnr_by_store[ctnr["DesignatedPhysicalStore"]] = ctnr

    def get_disk_info(self):
        self.disks = {}
        for i in self.disk_list:
            self.disks[i] = self.get("info", "-plist", i)

    def get_info(self):
        self.get_list()
        self.ctnr_by_ref = {}
        self.ctnr_by_store = {}
        self.get_apfs_list()
        self.get_disk_info()

    def find_system_disk(self):
        for name, dsk in self.disks.items():
            try:
                if dsk["VirtualOrPhysical"] == "Virtual":
                    continue
                if not dsk["Internal"]:
                    continue
                parts = self.disk_parts[name]["Partitions"]
                if parts[0]["Content"] == "Apple_APFS_ISC":
                    return name
            except (KeyError, IndexError):
                continue
        raise Exception("Could not find system disk")

    def get_partition_info(self, dev, refresh_apfs=False):
        partinfo = self.get("info", "-plist", dev)
        off = partinfo["PartitionMapPartitionOffset"]
        part = Partition(name=partinfo["DeviceIdentifier"], free=False,
                            type=partinfo["Content"],
                            offset=off, size=partinfo["Size"],
                            info=partinfo)
        if refresh_apfs:
            self.get_apfs_list(partinfo["APFSContainerReference"])

        if part.name in self.ctnr_by_store:
            part.container = self.ctnr_by_store[part.name]
            for t in (["System"], ["Data"], []):
                for vol in part.container["Volumes"]:
                    if vol["Roles"] == t:
                        part.label = vol["Name"]
                        break
                else:
                    continue
                break
        
        return part

    def get_partitions(self, dskname):
        dsk = self.disk_parts[dskname]
        parts = []
        total_size = dsk["Size"]
        p = 0
        prev_name = dskname
        for dskpart in dsk["Partitions"]:
            part = self.get_partition_info(dskpart["DeviceIdentifier"])
            if (part.offset - p) > self.FREE_THRESHOLD:
                parts.append(Partition(name=prev_name, free=True, type=None,
                                        offset=p, size=(part.offset - p)))
            parts.append(part)
            prev_name = part.name
            p = part.offset + part.size

        if (total_size - p) > self.FREE_THRESHOLD:
            parts.append(Partition(name=prev_name, free=True, type=None,
                                   offset=p, size=(total_size - p)))

        return parts

    def refresh_part(self, part):
        self.get_apfs_list(part.container["ContainerReference"])
        part.container = self.ctnr_by_store[part.name]

    def mount(self, target):
        self.action("quiet", "mount", target)
        info = self.get("info", "-plist", target)
        return info["MountPoint"]

    def addVolume(self, container, name, **kwargs):
        args = []
        for k, v in kwargs.items():
            args.extend(["-" + k, v])
        self.action("quiet", "apfs", "addVolume", container, "apfs", name, *args, verbose=True)

    def addPartition(self, after, fs, label, size):
        self.action("quiet", "addPartition", after, fs, label, size, verbose=True)
        disk = after.rsplit("s", 1)[0]
        self.get_list()
        for i, p in enumerate(self.disk_parts[disk]["Partitions"]):
            if after == p["DeviceIdentifier"]:
                break
        else:
            raise Exception("Could not find new partition")

        new = self.disk_parts[disk]["Partitions"][i + 1]
        return self.get_partition_info(new["DeviceIdentifier"],
                                       refresh_apfs=(fs == "apfs"))

    def changeVolumeRole(self, volume, role):
        self.action("quiet", "apfs", "changeVolumeRole", volume, role, verbose=True)

    def rename(self, volume, name):
        self.action("quiet", "rename", volume, name, verbose=True)
