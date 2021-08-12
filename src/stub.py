# SPDX-License-Identifier: MIT
import os, plistlib, shutil, sys, stat, subprocess, urlcache, zipfile
import osenum

class Installer:
    def __init__(self, sysinfo, dutil, osinfo, ipsw_info):
        self.dutil = dutil
        self.sysinfo = sysinfo
        self.osinfo = osinfo
        self.verbose = "-v" in sys.argv

        print("Downloading OS package info...")
        self.ucache = urlcache.URLCache(ipsw_info.url)
        self.ipsw = zipfile.ZipFile(self.ucache)
        self.ucache.flush_progress()
        print()

    def prepare_volume(self, part):
        self.part = part

        by_role = {}
        
        ctref = self.part.container["ContainerReference"]
        
        print("Preparing target volumes...")

        for volume in self.part.container["Volumes"]:
            by_role.setdefault(tuple(volume["Roles"]), []).append(volume)
        
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
                self.dutil.addVolume(ctref, label, role="D")
            self.dutil.refresh_part(self.part)
        else:
            self.label = label.rstrip(" - Data")

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
        if self.verbose:
            print()

    def check_volume(self, part=None):
        if part:
            self.part = part

        print("Checking volumes...")
        self.osi = self.osinfo.collect_one(self.part)
        
        if self.osi is None:
            raise Exception("Container is not ready for OS install")
        if self.verbose:
            print()

    def extract(self, src, dest):
        if self.verbose:
            print(f"  {src} -> {dest}/")
        self.ipsw.extract(src, dest)
        if self.verbose:
            self.ucache.flush_progress()

    def extract_file(self, src, dest, verbose=True, optional=True):
        try:
            with self.ipsw.open(src) as sfd, \
                open(dest, "wb") as dfd:
                if self.verbose and verbose:
                    print(f"  {src} -> {dest}")
                shutil.copyfileobj(sfd, dfd)
        except KeyError:
            if not optional:
                raise
        if self.verbose and verbose:
            self.ucache.flush_progress()

    def extract_tree(self, src, dest):
        if src[-1] != "/":
            src += "/"
        if self.verbose:
            print(f"  {src}* -> {dest}")

        infolist = self.ipsw.infolist()
        if self.verbose:
            self.ucache.flush_progress()

        for info in infolist:
            name = info.filename
            if not name.startswith(src):
                continue
            subpath = name[len(src):]
            assert subpath[0:1] != "/"

            destpath = os.path.join(dest, subpath)

            if info.is_dir():
                os.makedirs(destpath, exist_ok=True)
            elif stat.S_ISLNK(info.external_attr >> 16):
                link = self.ipsw.open(info.filename).read()
                if os.path.lexists(destpath):
                    os.unlink(destpath)
                os.symlink(link, destpath)
            else:
                self.extract_file(name, destpath, verbose=False)

            if self.verbose:
                self.ucache.flush_progress()

    def chflags(self, flags, path):
        subprocess.run(["chflags", flags, path], check=True)

    def install_files(self, cur_os):
        print("Beginning stub OS install...")
        ipsw = self.ipsw

        if self.verbose:
            print("Parsing metadata...")
        sysver = plistlib.load(ipsw.open("SystemVersion.plist"))
        manifest = plistlib.load(ipsw.open("BuildManifest.plist"))
        bootcaches = plistlib.load(ipsw.open("usr/standalone/bootcaches.plist"))
        self.ucache.flush_progress()
        
        for identity in manifest["BuildIdentities"]:
            if (identity["ApBoardID"] != hex(self.sysinfo.board_id) or
                identity["ApChipID"] != hex(self.sysinfo.chip_id) or
                identity["Info"]["DeviceClass"] != self.sysinfo.device_class or
                identity["Info"]["RestoreBehavior"] != "Erase" or
                identity["Info"]["Variant"] != "macOS Customer"):
                continue
            break
        else:
            raise Exception("Failed to locate a usable build identity for this device")

        if self.verbose:
            print(f'Using OS build {identity["Info"]["BuildNumber"]} for {self.sysinfo.device_class}')
            print()

        manifest["BuildIdentities"] = [identity]

        print("Setting up System volume...")

        self.extract("usr/standalone/bootcaches.plist", self.osi.system)
        shutil.copy("logo.icns", os.path.join(self.osi.system, ".VolumeIcon.icns"))

        cs = os.path.join(self.osi.system, "System/Library/CoreServices")
        os.makedirs(cs, exist_ok=True)
        sysver["ProductUserVisibleVersion"] += " (stub)"
        with open(os.path.join(cs, "SystemVersion.plist"), "wb") as fd:
            plistlib.dump(sysver, fd)
        self.extract("PlatformSupport.plist", cs)
        self.ucache.flush_progress()

        # Make the icon work
        subprocess.run(["xattr", "-wx", "com.apple.FinderInfo",
                        "0000000000000000040000000000000000000000000000000000000000000000",
                        self.osi.system], check=True)

        shutil.copy("m1n1.macho", os.path.join(self.osi.system))
        step2_sh = open("step2.sh").read().replace("##VGID##", self.osi.vgid)
        step2_sh_dst = os.path.join(self.osi.system, "step2.sh")
        with open(step2_sh_dst, "w") as fd:
            fd.write(step2_sh)
        os.chmod(step2_sh_dst, 0o755)
        self.step2_sh = step2_sh_dst

        if self.verbose:
            print()
        print("Setting up Data volume...")

        os.makedirs(os.path.join(self.osi.data, "private/var/db/dslocal"), exist_ok=True)

        if self.verbose:
            print()
        print("Setting up Preboot volume...")

        pb_vgid = os.path.join(self.osi.preboot, self.osi.vgid)
        os.makedirs(pb_vgid, exist_ok=True)
        
        bless2 = bootcaches["bless2"]
        
        restore_bundle = os.path.join(pb_vgid, bless2["RestoreBundlePath"])
        os.makedirs(restore_bundle, exist_ok=True)
        with open(os.path.join(restore_bundle, "BuildManifest.plist"), "wb") as fd:
            plistlib.dump(manifest, fd)
        self.extract("SystemVersion.plist", restore_bundle)
        self.extract("RestoreVersion.plist", restore_bundle)
        self.extract("usr/standalone/bootcaches.plist", restore_bundle)
        
        self.extract_tree("BootabilityBundle/Restore/Bootability",
                          os.path.join(restore_bundle, "Bootability"))
        self.extract_file("BootabilityBundle/Restore/Firmware/Bootability.dmg.trustcache",
                          os.path.join(restore_bundle, "Bootability/Bootability.trustcache"))

        self.extract_tree("Firmware/Manifests/restore/macOS Customer/", restore_bundle)

        copied = set()
        for key, val in identity["Manifest"].items():
            if key in ("BaseSystem", "OS", "Ap,SystemVolumeCanonicalMetadata"):
                continue
            path = val["Info"]["Path"]
            if path in copied:
                continue
            self.extract(path, restore_bundle)
            copied.add(path)
        
        self.ucache.flush_progress()

        os.makedirs(os.path.join(pb_vgid, "var/db"), exist_ok=True)
        admin_users = os.path.join(cur_os.os.preboot, cur_os.os.vgid, "var/db/AdminUserRecoveryInfo.plist")
        tg_admin_users = os.path.join(pb_vgid, "var/db/AdminUserRecoveryInfo.plist")

        if os.path.exists(tg_admin_users):
            self.chflags("noschg", tg_admin_users)
        shutil.copy(admin_users, tg_admin_users)
        
        # Stop macOS <12.0 bootability stufff from clobbering this file
        self.chflags("schg", tg_admin_users)

        # This is a workaround for some screwiness in the macOS <12.0 bootability
        # code, which ends up putting the apticket in the wrong volume...
        sys_restore_bundle = os.path.join(self.osi.system, bless2["RestoreBundlePath"])
        if os.path.lexists(sys_restore_bundle):
            os.unlink(sys_restore_bundle)
        os.symlink(restore_bundle, sys_restore_bundle)

        if self.verbose:
            print()
        print("Setting up Recovery volume...")

        rec_vgid = os.path.join(self.osi.recovery, self.osi.vgid)
        os.makedirs(rec_vgid, exist_ok=True)
        
        basesystem_path = os.path.join(rec_vgid, "usr/standalone/firmware")
        os.makedirs(basesystem_path, exist_ok=True)

        self.extract_file(identity["Manifest"]["BaseSystem"]["Info"]["Path"],
                          os.path.join(basesystem_path, "arm64eBaseSystem.dmg"))
        self.ucache.flush_progress()

        if self.verbose:
            print()
        print("Stub OS installation complete.")
        print()
