# SPDX-License-Identifier: MIT
import plistlib, subprocess, sys, logging
from dataclasses import dataclass

@dataclass
class Partition:
    name: str
    offset: int
    size: int
    free: bool
    type: str
    uuid: str = None
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
        if verbose == 2:
            capture = False
        elif verbose:
            capture = not self.verbose
        else:
            capture = True
        logging.debug(f"run: diskutil {args!r}")
        if capture:
            p = subprocess.run(["diskutil"] + list(args), check=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
            logging.debug(f"process output: {p.stdout}")
        else:
            subprocess.run(["diskutil"] + list(args), check=True)

    def get(self, *args):
        logging.debug(f"get: diskutil {args!r}")
        result = subprocess.run(["diskutil"] + list(args),
                                stdout=subprocess.PIPE, check=True)
        return plistlib.loads(result.stdout)

    def get_list(self):
        logging.info(f"DiskUtil.get_list()")
        self.list = self.get("list", "-plist")
        self.disk_list = self.list["WholeDisks"]
        logging.debug("  Whole disks:")
        for i in self.disk_list:
            logging.debug(f"  - {i!r}")
        self.disk_parts = {dsk["DeviceIdentifier"]: dsk for dsk in self.list["AllDisksAndPartitions"]}
        logging.debug("  All disks and partitions:")
        for k, v in self.disk_parts.items():
            logging.debug(f"  - {k}: {v!r}")

    def get_apfs_list(self, dev=None):
        logging.info(f"DiskUtil.get_apfs_list({dev=!r})")
        if dev:
            apfs = self.get("apfs", "list", dev, "-plist")
        else:
            apfs = self.get("apfs", "list", "-plist")
        for ctnr in apfs["Containers"]:
            vgs = self.get("apfs", "listVolumeGroups", ctnr["ContainerReference"], "-plist")
            logging.debug(f"container: {ctnr!r}")
            logging.debug(f"  VGs: {vgs!r}")
            ctnr["VolumeGroups"] = vgs["Containers"][0]["VolumeGroups"]
            self.ctnr_by_ref[ctnr["ContainerReference"]] = ctnr
            self.ctnr_by_store[ctnr["DesignatedPhysicalStore"]] = ctnr

    def get_disk_info(self):
        logging.info(f"DiskUtil.get_disk_info()")
        self.disks = {}
        for i in self.disk_list:
            self.disks[i] = self.get("info", "-plist", i)
            logging.debug(f" {i}: {self.disks[i]}")

    def get_info(self):
        logging.info(f"DiskUtil.get_info()")
        self.get_list()
        self.ctnr_by_ref = {}
        self.ctnr_by_store = {}
        self.get_apfs_list()
        self.get_disk_info()

    def find_system_disk(self):
        logging.info(f"DiskUtil.find_system_disk()")
        for name, dsk in self.disks.items():
            try:
                if dsk["VirtualOrPhysical"] == "Virtual":
                    continue
                if not dsk["Internal"]:
                    continue
                parts = self.disk_parts[name]["Partitions"]
                if parts[0]["Content"] == "Apple_APFS_ISC":
                    logging.info(f"System disk: {name}")
                    return name
            except (KeyError, IndexError):
                continue
        raise Exception("Could not find system disk")

    def get_partition_info(self, dev, refresh_apfs=False):
        logging.info(f"DiskUtil.get_partition_info({dev=!r}, {refresh_apfs=!r})")
        partinfo = self.get("info", "-plist", dev)
        off = partinfo["PartitionMapPartitionOffset"]
        part = Partition(name=partinfo["DeviceIdentifier"], free=False,
                            type=partinfo["Content"],
                            offset=off, size=partinfo["Size"],
                            uuid=partinfo["DiskUUID"],
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

        if part.container is None:
           part.container = {}
           part.container["Volumes"] = []
           logging.info(f"{part.name} doesn't have any Volumes")

        logging.debug("Partition {dev}: {part}")
        return part

    def get_partitions(self, dskname):
        logging.info(f"DiskUtil.get_partitions({dskname!r})")
        dsk = self.disk_parts[dskname]
        parts = []
        total_size = dsk["Size"]
        p = 0
        for dskpart in dsk["Partitions"]:
            parts.append(self.get_partition_info(dskpart["DeviceIdentifier"]))
        parts.sort(key=lambda i: i.offset)

        prev_name = dskname
        parts2 = []
        for part in parts:
            if (part.offset - p) > self.FREE_THRESHOLD:
                parts2.append(Partition(name=prev_name, free=True, type=None,
                                        offset=p, size=(part.offset - p)))
            parts2.append(part)
            prev_name = part.name
            p = part.offset + part.size

        if (total_size - p) > self.FREE_THRESHOLD:
            parts2.append(Partition(name=prev_name, free=True, type=None,
                                    offset=p, size=(total_size - p)))
        return parts2

    def refresh_part(self, part):
        logging.info(f"DiskUtil.refresh_part({part.name=!r})")
        self.get_apfs_list(part.container["ContainerReference"])
        part.container = self.ctnr_by_store[part.name]

    def mount(self, target):
        self.action("mount", target)
        info = self.get("info", "-plist", target)
        return info["MountPoint"]

    def addVolume(self, container, name, **kwargs):
        args = []
        for k, v in kwargs.items():
            args.extend(["-" + k, v])
        self.action("apfs", "addVolume", container, "apfs", name, *args, verbose=True)

    def addPartition(self, after, fs, label, size):
        size = str(size)
        self.action("addPartition", after, fs, label, size, verbose=True)

        disk = after.rsplit("s", 1)[0]

        self.get_list()
        parts = self.get_partitions(disk)

        for i, part in enumerate(parts):
            logging.info(f"Checking #{i} {part.name}...")
            if part.name == after:
                logging.info(f"Found previous partition {part.name}...")
                new_part = self.get_partition_info(parts[i + 1].name, refresh_apfs=(fs == "apfs"))
                logging.info(f"New partition: {new_part!r}")
                return new_part

        raise Exception("Could not find new partition")

    def changeVolumeRole(self, volume, role):
        self.action("apfs", "changeVolumeRole", volume, role, verbose=True)

    def rename(self, volume, name):
        self.action("rename", volume, name, verbose=True)

    def resizeContainer(self, name, size):
        size = str(size)
        self.action("apfs", "resizeContainer", name, size, verbose=2)
