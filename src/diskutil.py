# SPDX-License-Identifier: MIT
import plistlib, subprocess, sys, logging
from dataclasses import dataclass
from util import *

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

    def find_external_disks(self):
        logging.info(f"DiskUtil.find_external_disks()")
        disks = []
        for name, dsk in self.disks.items():
            try:
                if dsk["VirtualOrPhysical"] == "Virtual":
                    continue
                if dsk["Internal"]:
                    continue
                if dsk["BusProtocol"] != "USB":
                    continue
                if not dsk["Writable"]:
                    continue
                if not dsk["WholeDisk"]:
                    continue
                if "usb-drd" not in dsk["DeviceTreePath"]:
                    continue
                disks.append(dsk)
            except (KeyError, IndexError):
                continue

        return disks

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

        logging.debug(f"Partition {dev}: {part}")
        return part

    def get_disk_size(self, dskname):
        dsk = self.disk_parts[dskname]
        return dsk["Size"]

    def get_disk_usable_range(self, dskname):
        # GPT overhead aligned to 4K
        dsk = self.disk_parts[dskname]
        start = 40 * 512
        end = align_down(dsk["Size"] - 34 * 512, 4096)
        return start, end

    def get_partitions(self, dskname):
        logging.info(f"DiskUtil.get_partitions({dskname!r})")
        dsk = self.disk_parts[dskname]
        parts = []

        p, total_size = self.get_disk_usable_range(dskname)

        for dskpart in dsk.get("Partitions", []):
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

    def remount_rw(self, target):
        logging.info(f"DiskUtil.remount_rw({target})")
        subprocess.run(["mount", "-u", "-w", target], check=True)

    def addVolume(self, container, name, **kwargs):
        args = []
        for k, v in kwargs.items():
            args.extend(["-" + k, v])
        try:
            self.action("apfs", "addVolume", container, "apfs", name, *args, verbose=True)
        except subprocess.CalledProcessError as e:
            if e.output is not None and b"Mounting APFS Volume" in e.output:
                logging.warning(f"diskutil addVolume errored out spuriously, squelching: {e.output}")
            else:
                raise

    def partitionDisk(self, disk, fs, label, size):
        logging.info(f"DiskUtil.wipe_disk({disk}, {fs}, {label}, {size}")
        size = str(size)
        assert fs.lower() == "apfs"

        # diskutil likes to "helpfully" create an EFI partition for us...
        self.action("partitionDisk", disk, "1", "GPT", "free", "free", "0", verbose=True)

        self.get_list()
        parts = self.get_partitions(disk)
        assert len(parts) == 2 # EFI and free
        part = parts[0]

        # So re-format it as APFS...
        self.action("eraseVolume", fs, label, part.name)
        # And then grow it to the right size
        self.action("apfs", "resizeContainer", part.name, size)
        # Yes, this is silly.

        part = self.get_partition_info(part.name, refresh_apfs=(fs == "apfs"))
        logging.info(f"New partition: {part!r}")
        return part

    def addPartition(self, after, fs, label, size):
        logging.info(f"DiskUtil.addPartition({after}, {fs}, {label}, {size})")
        size = str(size)

        # diskutil can't create partitions on an empty disk...
        if (after in self.disk_parts
            and not self.disk_parts[after]["Partitions"]
            and fs.lower() == "apfs"):
            return self.partitionDisk(after, fs, label, size)

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

    def get_resize_limits(self, name):
        return self.get("apfs", "resizeContainer", name, "limits", "-plist")

    def resizeContainer(self, name, size):
        size = str(size)
        self.action("apfs", "resizeContainer", name, size, verbose=2)
