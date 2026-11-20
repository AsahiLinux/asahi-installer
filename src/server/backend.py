# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
from dataclasses import dataclass

import core.reporting as reporting
from core.installer import *
from server.messages import msg

PARTITION_LABELS = {
    "Apple_APFS_ISC": "Apple System Configuration",
    "Apple_APFS_Recovery": "macOS Recovery",
    "Apple_HFS": "Mac OS Extended (HFS+)",
    "Apple_Boot": "Apple Boot",
    "EFI": "EFI System Partition",
    "Microsoft Basic Data": "Basic Data",
}

MB = 10**6

def ceil_mb(n):
    return -(-n // MB)

def floor_mb(n):
    return n // MB

class PlanError(Exception):
    def __init__(self, message):
        super().__init__(message["key"])
        self.message = message

@dataclass
class Plan:
    edition: str
    template: dict
    target: object
    kind: str
    volume_name: str = None
    linux: int = 0
    alloc: int = None
    resize_to: int = None
    free_part: object = None
    resized: bool = False

class Backend:
    def __init__(self, version, expert=False, verbose=False):
        self.version = version
        self.expert = expert
        self.verbose = verbose
        self.progress_cb = None
        self.core = None
        self.blockers = []
        self.warnings = []
        self.parts = {}
        self.views = {}
        self.infos = {}

    def progress(self, fraction, rate):
        if self.progress_cb:
            self.progress_cb(fraction, rate)

    def collect(self):
        self.core = core = InstallerCore(self.version, self.progress, self.verbose)
        core.expert = self.expert
        self.blockers, self.warnings = [], []
        self.parts, self.views, self.infos = {}, {}, {}
        core.collect_system_info()
        try:
            core.check_system()
        except BuggyMacOSError:
            self.blockers.append(msg("blocker.buggy_macos"))
        except UnsupportedDeviceError:
            self.blockers.append(msg("blocker.unsupported_device"))
        except NoLoginUserError:
            self.blockers.append(msg("blocker.no_login_user"))
        except MacOSTooOldError as e:
            self.blockers.append(msg("blocker.macos_too_old", e.min_version))
        if not self.blockers:
            self.collect_disk()

    def collect_disk(self):
        core = self.core
        core.disk_info_init()
        core.collect_os_info()
        try:
            core.os_valid()
        except OSInvalidError:
            self.blockers.append(msg("blocker.no_primary_os"))
            return
        updated = False
        while True:
            try:
                core.user_valid()
                break
            except (NoAdminUsersError, UserNotAdminError) as e:
                if not updated:
                    core.update_preboot()
                    updated = True
                    continue
                if isinstance(e, NoAdminUsersError):
                    self.blockers.append(msg("blocker.no_admin_users"))
                else:
                    self.blockers.append(msg("blocker.user_not_admin", core.sysinfo.login_user))
                return
        if core.is_edu_128gb:
            self.warnings.append(msg("warning.edu_128gb"))
        actions = core.available_actions()
        if ACTION_INSTALL_FREE not in actions and ACTION_RESIZE not in actions:
            self.blockers.append(msg("blocker.no_space"))
        self.build_disk()

    @staticmethod
    def part_id(p):
        if p.uuid:
            return p.uuid.lower()
        return hashlib.sha1(f"{p.offset}:{p.size}".encode()).hexdigest()[:16]

    def smallest_edition(self):
        sizes = [self.core.template_min_size(t) for t in self.core.available_oses()]
        return min(sizes) if sizes else 0

    def build_disk(self):
        core = self.core
        smallest = self.smallest_edition()
        nolimits = core.expert or core.is_edu_128gb
        for p in core.partitions:
            pid = self.part_id(p)
            self.parts[pid] = p
            max_b, reason = 0, None
            if p.free:
                kind = "free"
                usable = align_down(p.size, PART_ALIGN)
                if not core.is_gpt:
                    reason = msg("disk.not_gpt")
                elif usable < smallest:
                    reason = msg("disk.free_too_small")
                else:
                    max_b = usable
            elif p.type == "Apple_APFS":
                kind = "apfs"
                try:
                    p.can_resize(nolimits)
                    info = core.get_resize_info(p)
                    self.infos[pid] = info
                    avail = max(0, align_down(info.total - align_up(info.min_size, PART_ALIGN), PART_ALIGN))
                    if not core.is_gpt:
                        reason = msg("disk.not_gpt")
                    elif avail < smallest:
                        reason = msg("disk.not_enough_to_reclaim")
                    else:
                        max_b = avail
                except APFSNoContainersError:
                    reason = msg("disk.no_container")
                except (PartitionNoFreeSpaceError, PartitionNotAPFSError):
                    reason = msg("disk.insufficient_free_space")
            else:
                kind = "other"
                label = PARTITION_LABELS.get(p.type, p.type)
                reason = msg("disk.unsuitable")
            current = core.cur_os is not None and any(o.vgid == core.cur_os.vgid for o in (p.os or []))
            self.views[pid] = dict(
                id=pid, kind=kind, label=label if kind == "other" else p.label, sizeMB=floor_mb(p.size),
                maxMB=floor_mb(max_b), reason=reason if max_b == 0 else None, isCurrentSystem=current,
                osLabels=[str(o) for o in (p.os or []) if o.version])

    def system(self):
        s = self.core.sysinfo
        return dict(
            expertMode=self.expert,
            device=dict(
                productName=s.product_name, soc=s.soc_name, osVersion=f"{s.macos_ver} ({s.macos_build})",
                bootMode=s.boot_mode, deviceClass=s.device_class, productType=s.product_type,
                boardId=hex(s.board_id), chipId=hex(s.chip_id), systemFirmware=s.sys_firmware,
                bootUuid=s.boot_uuid, bootVgid=s.boot_vgid, defaultBootVgid=s.default_boot,
                osRestoreVersion=s.macos_restore_ver, mainFirmwareVersion=f"{s.fsfr_ver} ({s.fsfr_build})",
                fallbackSystemFirmware=s.sys_firmware, sfrVersion=f"{s.sfr_ver} ({s.sfr_build})",
                systemRecoveryVersion=f"{s.sros_ver} ({s.sros_build})", loginUser=s.login_user),
            blockers=self.blockers, warnings=self.warnings)

    def template(self, edition):
        for t in self.core.available_oses():
            if edition_id(t) == edition:
                return t
        return None

    def availability(self, t):
        if self.blockers:
            return False, msg("edition.blocked")
        try:
            self.core.available_ipsws(t.get("supported_fw", None))
        except FirmwareTooOldError as e:
            return False, msg("edition.firmware_too_old", e.min_version)
        return True, None

    def editions(self):
        out = []
        for t in self.core.available_oses():
            ok, reason = self.availability(t)
            out.append(dict(id=edition_id(t), name=t["name"], minMB=ceil_mb(self.core.template_min_size(t)),
                            available=ok, unavailableReason=reason))
        return out

    def disk(self):
        core = self.core
        return dict(sizeMB=floor_mb(core.dutil.get_disk_size(core.sys_disk)), isGpt=core.is_gpt,
                    partitions=[self.views[self.part_id(p)] for p in core.partitions])

    def bounds(self, kind, part, info, edition_min, expandable):
        core = self.core
        if kind == "free":
            usable = align_down(part.size, PART_ALIGN)
            if expandable or usable < edition_min:
                return edition_min, usable, usable
            return edition_min, edition_min, edition_min
        if kind == "apfs" and info is not None:
            min_b = edition_min if core.expert else max(edition_min, MIN_INSTALL_FREE + PART_ALIGN)
            max_b = max(0, align_down(info.total - align_up(info.min_size, PART_ALIGN), PART_ALIGN))
            keep = max(info.total // 2, info.min_size)
            default_b = min(max(align_down(info.total - keep, PART_ALIGN), min_b), max(max_b, min_b))
            return min_b, max_b, default_b
        return 0, 0, 0

    def plan(self, edition, target, size_mb, auth_locked=False):
        core = self.core
        t = self.template(edition)
        if t is None:
            raise PlanError(msg("plan.unknown_edition"))
        part = self.parts.get(target)
        if part is None:
            raise PlanError(msg("plan.unknown_target"))
        view = self.views[target]
        kind = view["kind"]
        info = self.infos.get(target)
        problems, warnings = [], []
        expandable = any(p.get("expand", False) for p in t["partitions"])
        edition_min = core.template_min_size(t)
        fixed = kind == "free" and not expandable

        if not self.availability(t)[0]:
            problems.append(msg("plan.edition_unavailable"))
        if auth_locked:
            problems.append(msg("plan.auth_locked"))
        if not core.is_gpt:
            problems.append(msg("plan.not_gpt"))

        min_b, max_b, default_b = self.bounds(kind, part, info, edition_min, expandable)
        linux = 0
        if kind == "other":
            problems.append(msg("plan.target_unusable"))
        elif kind == "apfs" and info is None:
            problems.append(msg("plan.target_not_resizable"))
        elif min_b > max_b:
            problems.append(msg("plan.not_enough_space", ceil_mb(min_b), floor_mb(max_b)))
        else:
            req = align_up(size_mb * MB if size_mb is not None else default_b, PART_ALIGN)
            if fixed:
                if size_mb is not None and req != min_b:
                    warnings.append(msg("plan.size_fixed", ceil_mb(min_b)))
                req = min_b
            elif req < min_b:
                problems.append(msg("plan.size_too_small", ceil_mb(min_b)))
            elif req > max_b:
                problems.append(msg("plan.size_too_large", floor_mb(max_b)))
            linux = min(max(req, min_b), max_b)

        stub = STUB_SIZE
        os_b = (edition_min - stub) if (fixed and linux) else max(0, linux - stub)
        macos_after = free_after = resize_to = None
        if linux and kind == "apfs":
            resize_to = macos_after = align_down(info.total - linux, PART_ALIGN)
            if info.has_large_overhead:
                warnings.append(msg("plan.large_overhead"))
            if view["isCurrentSystem"]:
                warnings.append(msg("plan.resizing_current_system"))
            if core.expert and not info.frees_enough_for_install(resize_to):
                warnings.append(msg("plan.too_little_freed_expert"))
        elif linux and kind == "free":
            free_after = part.size - (stub + os_b if fixed else linux)

        plan = Plan(edition=edition, template=t, target=part, kind=kind, linux=linux,
                    alloc=linux if expandable else None, resize_to=resize_to,
                    free_part=part if kind == "free" else None)
        result = dict(
            valid=not problems,
            limits=dict(minMB=ceil_mb(min_b), maxMB=(ceil_mb if fixed else floor_mb)(max_b), stepMB=1,
                        defaultMB=(ceil_mb if fixed else floor_mb)(default_b)),
            normalised=dict(linuxMB=floor_mb(linux), stubMB=floor_mb(stub), osMB=floor_mb(os_b),
                            macosAfterMB=None if macos_after is None else floor_mb(macos_after),
                            freeAfterMB=None if free_after is None else floor_mb(free_after)),
            warnings=warnings, problems=problems)
        return result, plan

    @staticmethod
    def volume_name_valid(name):
        return bool(name) and name == name.strip() and len(name.encode("utf-8")) <= 127 \
            and not any(ord(c) < 0x20 or c in "/:" for c in name)

    def default_volume_name(self, edition):
        return self.template(edition)["default_os_name"]

    def prepare(self, plan):
        core = self.core
        core.stage = "preparing"
        core.load_os_package(plan.template)
        ipsws = core.available_ipsws(plan.template.get("supported_fw", None))
        core.load_ipsw(ipsws[-1])
        core.osins.name = plan.volume_name

    def resize(self, plan):
        core = self.core
        core.resize_partition(plan.target, plan.resize_to)
        plan.resized = True
        uuid = plan.target.uuid
        core.disk_info_init()
        core.collect_os_info()
        idx = next(i for i, p in enumerate(core.partitions) if p.uuid == uuid)
        plan.free_part = next(p for p in core.partitions[idx + 1:] if p.free)

    def install(self, plan):
        self.core.install_into_free(plan.free_part, plan.alloc)

    def request_cancel(self):
        self.core.request_cancel()

    def auth_users(self):
        return list(self.core.admin_candidates())

    def check_credentials(self, user, password):
        return self.core.check_credentials(user, password)

    def step2_mode(self):
        return self.core.step2_mode()

    def run_step2_script(self):
        self.core.run_step2_script()

    def set_reduced_security(self, user, password):
        self.core.set_admin_credentials(user, password)
        self.core.set_reduced_security()

    def bless(self, user, password):
        self.core.set_admin_credentials(user, password)
        self.core.bless()

    def finalise(self, plan):
        self.core.hide_new_volume()
        info = self.core.get_install_info()
        mode = self.core.step2_mode()
        next_step = {STEP2_DIRECT: "direct", STEP2_RECOVERY: "recovery"}.get(mode, "macos")
        return dict(nextStep=next_step, volumeName=plan.volume_name, vgid=info.vgid, efiPartuuid=info.efi_partuuid)

    def disk_state(self, plan):
        core = self.core
        if core.stage == "preparing":
            return "unchanged"
        if core.stage == "resizing":
            return "unknown"
        if core.stage == "installing":
            if core.part is None:
                return "resized_not_installed" if plan.resized else "unchanged"
            return "partial_install"
        return "partial_install"

    def telemetry(self):
        config = reporting.get_report_config()
        if config is None:
            return False, None, None
        url, tag = config
        return True, reporting.build_report(self.core, tag), url

    def send_telemetry(self, url, payload):
        return reporting.send_report(url, payload)

    def shutdown(self):
        self.core.shutdown()

    def reboot(self):
        self.core.reboot()
