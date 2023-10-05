# SPDX-License-Identifier: MIT
import os, os.path, plistlib, shutil, sys, stat, subprocess, urlcache, zipfile, logging, json
import osenum
from asahi_firmware.wifi import WiFiFWCollection
from asahi_firmware.bluetooth import BluetoothFWCollection
from asahi_firmware.multitouch import MultitouchFWCollection
from asahi_firmware.kernel import KernelFWCollection
from asahi_firmware.isp import ISPFWCollection
from util import *

class StubInstaller(PackageInstaller):
    def __init__(self, sysinfo, dutil, osinfo):
        super().__init__()
        self.dutil = dutil
        self.sysinfo = sysinfo
        self.osinfo = osinfo
        self.ucache = None
        self.copy_idata = []
        self.stub_info = {}
        self.pkg = None

    def load_ipsw(self, ipsw_info):
        self.install_version = ipsw_info.version.split(maxsplit=1)[0]

        base = os.environ.get("IPSW_BASE", None)
        url = ipsw_info.url
        if base:
            url = base + "/" + os.path.split(url)[-1]

        logging.info(f"IPSW URL: {url}")
        if url.startswith("http"):
            p_progress("Downloading macOS OS package info...")
            self.ucache = urlcache.URLCache(url)
            self.pkg = zipfile.ZipFile(self.ucache)
        else:
            p_progress("Loading macOS OS package info...")
            self.pkg = zipfile.ZipFile(open(url, "rb"))
        self.flush_progress()
        logging.info(f"OS package opened")
        print()

    def prepare_volume(self, part):
        logging.info(f"StubInstaller.prepare_volume({part.name=!r})")
        self.part = part

        by_role = {}

        ctref = self.part.container["ContainerReference"]

        p_progress("Preparing target volumes...")

        for volume in self.part.container["Volumes"]:
            roles = tuple(volume["Roles"])
            logging.info(f" {volume['DeviceIdentifier']} roles: {roles}")
            by_role.setdefault(roles, []).append(volume)

        for role in ("Preboot", "Recovery", "Data", "System"):
            vols = by_role.get(role, [])
            if len(vols) > 1:
                raise Exception(f"Multiple {role} volumes")

        self.label = self.part.label or "Linux"
        if not by_role.get(("Data",), None):
            if default_vol := by_role.get((), None):
                self.dutil.changeVolumeRole(default_vol[0]["DeviceIdentifier"], "D")
                self.dutil.rename(default_vol[0]["DeviceIdentifier"], self.label + " - Data")
            else:
                self.dutil.addVolume(ctref, self.label, role="D")
            self.dutil.refresh_part(self.part)
        else:
            self.label = self.label.rstrip(" - Data")

        for volume in self.part.container["Volumes"]:
            if volume["Roles"] == ["Data",]:
                data_volume = volume["DeviceIdentifier"]
                break
        else:
            raise Exception("Could not find Data volume")

        if not by_role.get(("System",), None):
            self.dutil.addVolume(ctref, self.label, role="S", groupWith=data_volume)

        if not by_role.get(("Preboot",), None):
            self.dutil.addVolume(ctref, "Preboot", role="B")

        if not by_role.get(("Recovery",), None):
            self.dutil.addVolume(ctref, "Recovery", role="R")

        self.dutil.refresh_part(self.part)

    def check_volume(self, part=None):
        if part:
            self.part = part

        logging.info(f"StubInstaller.check_volume({self.part.name=!r})")

        p_progress("Checking volumes...")
        os = self.osinfo.collect_part(self.part)

        if len(os) != 1:
            raise Exception("Container is not ready for OS install")

        self.osi = os[0]

    def chflags(self, flags, path):
        logging.info(f"chflags {flags} {path}")
        subprocess.run(["chflags", flags, path], check=True)

    def get_paths(self):
        self.resources = os.path.join(self.osi.system, "Finish Installation.app/Contents/Resources")
        self.step2_sh = os.path.join(self.resources, "step2.sh")
        self.boot_obj_path = os.path.join(self.resources, "boot.bin")
        self.iapm_path = os.path.join(self.osi.system, ".IAPhysicalMedia")
        self.iapm_dis_path = os.path.join(self.osi.system, "IAPhysicalMedia-disabled.plist")
        self.core_services = os.path.join(self.osi.system, "System/Library/CoreServices")
        self.sv_path = os.path.join(self.core_services, "SystemVersion.plist")
        self.sv_dis_path = os.path.join(self.core_services, "SystemVersion-disabled.plist")
        self.icon_path = os.path.join(self.osi.system, ".VolumeIcon.icns")

    def check_existing_install(self, osi):
        self.osi = osi
        self.get_paths()

        if not os.path.exists(self.step2_sh):
            logging.error("step2.sh is missing")
            return False
        if not os.path.exists(self.boot_obj_path):
            logging.error("boot.bin is missing")
            return False
        if not any(os.path.exists(i) for i in (self.iapm_path, self.iapm_dis_path)):
            logging.error(".IAPhysicalMedia is missing")
            return False
        if not any(os.path.exists(i) for i in (self.sv_path, self.sv_dis_path)):
            logging.error("SystemVersion is missing")
            return False

        return True

    def prepare_for_bless(self):
        if not os.path.exists(self.sv_path):
            os.replace(self.sv_dis_path, self.sv_path)

    def prepare_for_step2(self):
        if os.path.exists(self.sv_path):
            os.replace(self.sv_path, self.sv_dis_path)
        if not os.path.exists(self.iapm_path):
            os.replace(self.iapm_dis_path, self.iapm_path)

    def install_files(self, cur_os):
        logging.info("StubInstaller.install_files()")
        logging.info(f"VGID: {self.osi.vgid}")
        logging.info(f"OS info: {self.osi}")

        p_progress("Beginning stub OS install...")
        ipsw = self.pkg

        self.get_paths()

        logging.info("Parsing metadata...")

        sysver = plistlib.load(ipsw.open("SystemVersion.plist"))
        manifest = plistlib.load(ipsw.open("BuildManifest.plist"))
        bootcaches = plistlib.load(ipsw.open("usr/standalone/bootcaches.plist"))
        self.flush_progress()

        self.manifest = manifest
        for identity in manifest["BuildIdentities"]:
            if (identity["ApBoardID"] != f'0x{self.sysinfo.board_id:02X}' or
                identity["ApChipID"] != f'0x{self.sysinfo.chip_id:04X}' or
                identity["Info"]["DeviceClass"] != self.sysinfo.device_class or
                identity["Info"]["RestoreBehavior"] != "Erase" or
                identity["Info"]["Variant"] != "macOS Customer"):
                continue
            break
        else:
            raise Exception("Failed to locate a usable build identity for this device")

        logging.info(f'Using OS build {identity["Info"]["BuildNumber"]} for {self.sysinfo.device_class}')

        self.all_identities = manifest["BuildIdentities"]
        self.identity = identity
        manifest["BuildIdentities"] = [identity]

        self.stub_info.update({
            "vgid": self.osi.vgid,
            "system_version": sysver,
            "manifest_info": {
                "build_number": identity["Info"]["BuildNumber"],
                "variant": identity["Info"]["Variant"],
                "device_class": identity["Info"]["DeviceClass"],
                "board_id": identity["ApBoardID"],
                "chip_id": identity["ApChipID"],
            }
        })

        p_progress("Setting up System volume...")
        logging.info("Setting up System volume")

        self.extract("usr/standalone/bootcaches.plist", self.osi.system)
        shutil.copy("logo.icns", self.icon_path)

        cs = os.path.join(self.osi.system, "System/Library/CoreServices")
        os.makedirs(cs, exist_ok=True)
        sysver["ProductUserVisibleVersion"] += " (stub)"
        self.extract("PlatformSupport.plist", cs)
        self.flush_progress()

        # Make the icon work
        try:
            logging.info(f"xattr -wx com.apple.FinderInfo .... {self.osi.system}")
            subprocess.run(["xattr", "-wx", "com.apple.FinderInfo",
                           "0000000000000000040000000000000000000000000000000000000000000000",
                           self.osi.system], check=True)
        except:
            p_error("Failed to apply extended attributes, logo will not work.")

        p_progress("Setting up Data volume...")
        logging.info("Setting up Data volume")

        os.makedirs(os.path.join(self.osi.data, "private/var/db/dslocal"), exist_ok=True)

        p_progress("Setting up Preboot volume...")
        logging.info("Setting up Preboot volume")

        pb_vgid = os.path.join(self.osi.preboot, self.osi.vgid)
        os.makedirs(pb_vgid, exist_ok=True)

        bless2 = bootcaches["bless2"]

        restore_bundle = os.path.join(pb_vgid, bless2["RestoreBundlePath"])
        os.makedirs(restore_bundle, exist_ok=True)
        restore_manifest = os.path.join(restore_bundle, "BuildManifest.plist")
        with open(restore_manifest, "wb") as fd:
            plistlib.dump(manifest, fd)
        self.copy_idata.append((restore_manifest, "BuildManifest.plist"))
        self.extract("SystemVersion.plist", restore_bundle)
        self.extract("RestoreVersion.plist", restore_bundle)
        self.copy_idata.append((os.path.join(restore_bundle, "RestoreVersion.plist"),
                                "RestoreVersion.plist"))
        self.extract("usr/standalone/bootcaches.plist", restore_bundle)

        self.extract_tree("BootabilityBundle/Restore/Bootability",
                          os.path.join(restore_bundle, "Bootability"))
        self.extract_file("BootabilityBundle/Restore/Firmware/Bootability.dmg.trustcache",
                          os.path.join(restore_bundle, "Bootability/Bootability.trustcache"))

        self.extract_tree("Firmware/Manifests/restore/macOS Customer/", restore_bundle)

        copied = set()
        self.kernel_path = None
        for key, val in identity["Manifest"].items():
            if key in ("BaseSystem", "OS", "Ap,SystemVolumeCanonicalMetadata"):
                continue
            if key.startswith("Cryptex"):
                continue
            path = val["Info"]["Path"]
            if path in copied:
                continue
            self.extract(path, restore_bundle)
            if path.startswith("kernelcache."):
                name = os.path.basename(path)
                self.copy_idata.append((os.path.join(restore_bundle, name), name))
                if self.kernel_path is None:
                    self.kernel_path = os.path.join(restore_bundle, name)
            copied.add(path)

        self.flush_progress()

        os.makedirs(os.path.join(pb_vgid, "var/db"), exist_ok=True)
        admin_users = os.path.join(cur_os.preboot, cur_os.vgid, "var/db/AdminUserRecoveryInfo.plist")
        tg_admin_users = os.path.join(pb_vgid, "var/db/AdminUserRecoveryInfo.plist")
        if os.path.exists(tg_admin_users):
            self.chflags("noschg", tg_admin_users)
        shutil.copy(admin_users, tg_admin_users)

        self.copy_idata.append((tg_admin_users, "AdminUserRecoveryInfo.plist"))

        admin_users = plistlib.load(open(tg_admin_users, "rb"))
        self.stub_info["admin_users"] = {}
        for user, info in admin_users.items():
            self.stub_info["admin_users"][user] = {
                "uid": info["GeneratedUID"],
                "real_name": info["RealName"],
            }

        # Stop macOS <12.0 bootability stufff from clobbering this file
        self.chflags("schg", tg_admin_users)

        # This is a workaround for some screwiness in the macOS <12.0 bootability
        # code, which ends up putting the apticket in the wrong volume...
        sys_restore_bundle = os.path.join(self.osi.system, bless2["RestoreBundlePath"])
        if os.path.lexists(sys_restore_bundle):
            os.unlink(sys_restore_bundle)
        os.symlink(restore_bundle, sys_restore_bundle)

        p_progress("Setting up Recovery volume...")
        logging.info("Setting up Recovery volume")

        rec_vgid = os.path.join(self.osi.recovery, self.osi.vgid)
        os.makedirs(rec_vgid, exist_ok=True)

        basesystem_path = os.path.join(rec_vgid, "usr/standalone/firmware")
        os.makedirs(basesystem_path, exist_ok=True)

        logging.info("Extracting arm64eBaseSystem.dmg")
        self.copy_compress(identity["Manifest"]["BaseSystem"]["Info"]["Path"],
                          os.path.join(basesystem_path, "arm64eBaseSystem.dmg"))
        self.flush_progress()

        p_progress("Wrapping up...")

        logging.info("Writing SystemVersion.plist")
        with open(self.sv_path, "wb") as fd:
            plistlib.dump(sysver, fd)
        self.copy_idata.append((self.sv_path, "SystemVersion.plist"))

        if os.path.exists(self.sv_dis_path):
            os.remove(self.sv_dis_path)

        logging.info("Copying Finish Installation.app")
        shutil.copytree("step2/Finish Installation.app",
                        os.path.join(self.osi.system, "Finish Installation.app"))

        logging.info("Writing step2.sh")
        step2_sh = open("step2/step2.sh").read()
        step2_sh = step2_sh.replace("##VGID##", self.osi.vgid)
        step2_sh = step2_sh.replace("##PREBOOT##", self.osi.preboot_vgid)
        with open(self.step2_sh, "w") as fd:
            fd.write(step2_sh)
        os.chmod(self.step2_sh, 0o755)

        logging.info("Copying .IAPhysicalMedia")
        shutil.copy("step2/IAPhysicalMedia.plist", self.iapm_path)

        if os.path.exists(self.iapm_dis_path):
            os.remove(self.iapm_dis_path)

        print()
        p_success("Stub OS installation complete.")
        logging.info("Stub OS installed")
        print()

    def collect_firmware(self, pkg):
        p_progress("Collecting firmware...")
        logging.info("StubInstaller.collect_firmware()")

        logging.info("Collecting FUD firmware")
        if os.path.exists("fud_firmware"):
            shutil.rmtree("fud_firmware")

        os.makedirs("fud_firmware", exist_ok=True)
        copied = set()
        for identity in [self.identity]:
            if (identity["Info"]["RestoreBehavior"] != "Erase" or
                identity["Info"]["Variant"] != "macOS Customer"):
                continue
            device = identity["Info"]["DeviceClass"]
            if not device.endswith("ap"):
                continue
            logging.info(f"Collecting FUD firmware for device {device}")
            device = device[:-2]
            for key, val in identity["Manifest"].items():
                if key in ("BaseSystem", "OS", "Ap,SystemVolumeCanonicalMetadata",
                           "StaticTrustCache", "SystemVolume"):
                    continue
                path = val["Info"]["Path"]
                if (not val["Info"].get("IsFUDFirmware", False)
                    or val["Info"].get("IsLoadedByiBoot", False)
                    or val["Info"].get("IsLoadedByiBootStage1", False)
                    or not path.endswith(".im4p")):
                    continue
                if path not in copied:
                    self.extract(path, "fud_firmware")
                    copied.add(path)
                fud_dir = os.path.join("fud_firmware", device)
                os.makedirs(fud_dir, exist_ok=True)
                os.symlink(os.path.join("..", path),
                           os.path.join(fud_dir, key + ".im4p"))

        img = os.path.join(self.osi.recovery, self.osi.vgid,
                           "usr/standalone/firmware/arm64eBaseSystem.dmg")
        logging.info("Attaching recovery ramdisk")
        subprocess.run(["hdiutil", "attach", "-quiet", "-readonly", "-mountpoint", "recovery", img],
                       check=True)
        logging.info("Collecting WiFi firmware")
        col = WiFiFWCollection("recovery/usr/share/firmware/wifi/")
        pkg.add_files(sorted(col.files()))
        logging.info("Collecting Bluetooth firmware")
        col = BluetoothFWCollection("recovery/usr/share/firmware/bluetooth/")
        pkg.add_files(sorted(col.files()))
        logging.info("Collecting Multitouch firmware")
        col = MultitouchFWCollection("fud_firmware/")
        pkg.add_files(sorted(col.files()))
        logging.info("Collecting ISP firmware")
        col = ISPFWCollection("recovery/usr/sbin/")
        pkg.add_files(sorted(col.files()))
        logging.info("Collecting Kernel firmware")
        col = KernelFWCollection(self.kernel_path)
        pkg.add_files(sorted(col.files()))
        logging.info("Making fallback firmware archive")
        subprocess.run(["tar", "czf", "all_firmware.tar.gz",
                        "fud_firmware",
                        "-C", "recovery/usr/share", "firmware",
                        "-C", "../../usr/sbin", "appleh13camerad",
                       ], check=True)
        self.copy_idata.append(("all_firmware.tar.gz", "all_firmware.tar.gz"))
        logging.info("Detaching recovery ramdisk")
        subprocess.run(["hdiutil", "detach", "-quiet", "recovery"])

    def collect_installer_data(self, path):
        p_progress("Collecting installer data...")
        logging.info(f"Copying installer data to {path}")

        for src, name in self.copy_idata:
            shutil.copy(src, os.path.join(path, name))

        with open(os.path.join(path, "stub_info.json"), "w") as fd:
            json.dump(self.stub_info, fd)
