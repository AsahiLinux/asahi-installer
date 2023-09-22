# SPDX-License-Identifier: MIT
import os, shutil, sys, stat, subprocess, urlcache, zipfile, logging

import m1n1
from util import *

class OSInstaller(PackageInstaller):
    PART_ALIGNMENT = 1024 * 1024
    def __init__(self, dutil, data, template):
        super().__init__()
        self.dutil = dutil
        self.data = data
        self.template = template
        self.name = template["default_os_name"]
        self.ucache = None
        self.efi_part = None
        self.idata_targets = []
        self.install_size = self.min_size

    @property
    def default_os_name(self):
        return self.template["default_os_name"]
    @property
    def min_size(self):
        return sum(self.align(psize(part["size"])) for part in self.template["partitions"])
    @property
    def expandable(self):
        return any(part.get("expand", False) for part in self.template["partitions"])
    @property
    def needs_firmware(self):
        return any(p.get("copy_firmware", False) for p in self.template["partitions"])

    def align(self, v):
        return align_up(v, self.PART_ALIGNMENT)

    def load_package(self):
        package = self.template.get("package", None)
        if not package:
            return

        if not package.startswith("http"):
            package = os.environ.get("REPO_BASE", ".") + "/os/" + package

        logging.info(f"OS package URL: {package}")
        if package.startswith("http"):
            p_progress("Downloading OS package info...")
            self.ucache = urlcache.URLCache(package)
            self.pkg = zipfile.ZipFile(self.ucache)
        else:
            p_progress("Loading OS package info...")
            self.pkg = zipfile.ZipFile(open(package, "rb"))
        self.flush_progress()
        logging.info(f"OS package opened")

    def flush_progress(self):
        if self.ucache:
            self.ucache.flush_progress()

    def partition_disk(self, prev, total_size=None):
        self.part_info = []
        logging.info("OSInstaller.partition_disk({prev}=!r)")

        if total_size is None:
            expand_size = 0
        else:
            expand_size = total_size - self.min_size
            self.install_size = total_size
            assert expand_size >= 0

        for part in self.template["partitions"]:
            logging.info(f"Adding partition: {part}")

            size = self.align(psize(part["size"]))
            ptype = part["type"]
            fmt = part.get("format", None)
            name = f"{part['name']} - {self.name}"
            logging.info(f"Partition Name: {name}")
            if part.get("expand", False):
                size += expand_size
                logging.info(f"Expanded to {size} (+{expand_size})")

            p_progress(f"Adding partition {part['name']} ({ssize(size)})...")
            info = self.dutil.addPartition(prev, f"%{ptype}%", "%noformat%", size)
            if ptype == "EFI":
                self.efi_part = info
            self.part_info.append(info)
            if fmt == "fat":
                p_plain("  Formatting as FAT...")
                args = ["newfs_msdos", "-F", "32",
                        "-v", name[:11]]
                if "volume_id" in part:
                    args.extend(["-I", part["volume_id"]])
                args.append(f"/dev/r{info.name}")
                logging.info(f"Run: {args!r}")
                subprocess.run(args, check=True, stdout=subprocess.PIPE)
            elif fmt:
                raise Exception(f"Unsupported format {fmt}")

            prev = info.name

    def download_extras(self):
        p_progress("Downloading extra files...")
        logging.info("OSInstaller.download_extras()")

        mountpoint = self.dutil.mount(self.efi_part.name)
        dest = os.path.join(mountpoint, "asahi", "extras")
        os.makedirs(dest, exist_ok=True)

        count = len(self.template["extras"])
        for i, url in enumerate(self.template["extras"]):
            base = os.path.basename(url)
            p_plain(f"  Downloading {base} ({i + 1}/{count})...")
            ucache = urlcache.URLCache(url)
            data = ucache.read()
            with open(os.path.join(dest, base), "wb") as fd:
                fd.write(data)

    def install(self, stub_ins):
        p_progress("Installing OS...")
        logging.info("OSInstaller.install()")

        # Force a reconnect, since the connection is likely to have timed out
        if self.ucache is not None:
            self.ucache.close_connection()

        icon = self.template.get("icon", None)
        if icon:
            self.extract_file(icon, stub_ins.icon_path)
            self.flush_progress()

        for part, info in zip(self.template["partitions"], self.part_info):
            logging.info(f"Installing partition {part!r} -> {info.name}")
            image = part.get("image", None)
            if image:
                p_plain(f"  Extracting {image} into {info.name} partition...")
                logging.info(f"Extract: {image}")
                zinfo = self.pkg.getinfo(image)
                with self.pkg.open(image) as sfd, \
                    open(f"/dev/r{info.name}", "r+b") as dfd:
                    self.fdcopy(sfd, dfd, zinfo.file_size)
                self.flush_progress()
            source = part.get("source", None)
            if source:
                p_plain(f"  Copying from {source} into {info.name} partition...")
                mountpoint = self.dutil.mount(info.name)
                logging.info(f"Copy: {source} -> {mountpoint}")
                self.extract_tree(source, mountpoint)
                self.flush_progress()
            if part.get("copy_firmware", False):
                mountpoint = self.dutil.mount(info.name)
                p_plain(f"  Copying firmware into {info.name} partition...")
                base = os.path.join(mountpoint, "vendorfw")
                logging.info(f"Firmware -> {base}")
                shutil.copytree(self.firmware_package.path, base)
            if part.get("copy_installer_data", False):
                mountpoint = self.dutil.mount(info.name)
                data_path = os.path.join(mountpoint, "asahi")
                os.makedirs(data_path, exist_ok=True)
                self.idata_targets.append(data_path)

        if "extras" in self.template:
            assert self.efi_part is not None
            self.download_extras()

        p_progress("Preparing to finish installation...")

        logging.info(f"Building boot object")
        boot_object = self.template["boot_object"]
        next_object = self.template.get("next_object", None)
        logging.info(f"  Boot object: {boot_object}")
        logging.info(f"  Next object: {next_object}")

        m1n1_vars = []
        if self.efi_part:
            m1n1_vars.append(f"chosen.asahi,efi-system-partition={self.efi_part.uuid.lower()}")
        if next_object is not None:
            assert self.efi_part is not None
            m1n1_vars.append(f"chainload={self.efi_part.uuid.lower()};{next_object}")

        logging.info(f"m1n1 vars:")
        for i in m1n1_vars:
            logging.info(f"  {i}")

        m1n1.build(os.path.join("boot", boot_object), stub_ins.boot_obj_path, m1n1_vars)

        logging.info(f"Built boot object at {stub_ins.boot_obj_path}")
