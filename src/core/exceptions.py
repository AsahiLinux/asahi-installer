# SPDX-License-Identifier: GPL-2.0-or-later

class OSInvalidError(Exception):
    """The current OS is invalid/has been enumerated incorrectly"""
    pass

class NoAdminUsersError(Exception):
    """There are no machine administrators registered on this Mac"""
    pass

class UserNotAdminError(Exception):
    """The current user is not a machine administrator"""
    pass

class PartitionNotAPFSError(Exception):
    """The partition is not an APFS partition"""
    pass

class APFSNoContainersError(Exception):
    """The APFS partition has no containers"""
    pass

class PartitionNoFreeSpaceError(Exception):
    """The partition has insufficient free space"""
    pass

class FsctlError(Exception):
    """An APFS fsctl call failed"""
    pass

class BuggyMacOSError(Exception):
    """The running macOS version has bugs that make installation unsafe"""
    pass

class UnsupportedDeviceError(Exception):
    """This device is not supported"""
    pass

class NoLoginUserError(Exception):
    """No user is logged into the local console"""
    pass

class MacOSTooOldError(Exception):
    """The running macOS version is older than the minimum supported one"""
    def __init__(self, min_version):
        super().__init__(min_version)
        self.min_version = min_version

class FirmwareTooOldError(Exception):
    """The system firmware is too old for any available IPSW"""
    def __init__(self, min_version):
        super().__init__(min_version)
        self.min_version = min_version
