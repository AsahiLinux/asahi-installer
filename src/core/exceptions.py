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

class ExistingInstallError(Exception):
    """The existing installation is missing files"""
    pass

class M1n1VarsError(Exception):
    """The m1n1 variables could not be read from the boot object"""
    def __init__(self, path):
        super().__init__(path)
        self.path = path

class EspNotFoundError(Exception):
    """The EFI system partition of an install could not be determined"""
    pass

class UnsupportedVersionError(Exception):
    """The install uses a macOS version that is not supported"""
    def __init__(self, version):
        super().__init__(version)
        self.version = version

class SizeTooSmallError(Exception):
    """The requested size is below the minimum"""
    def __init__(self, limit):
        super().__init__(limit)
        self.limit = limit

class SizeTooLargeError(Exception):
    """The requested size is above the maximum"""
    def __init__(self, limit):
        super().__init__(limit)
        self.limit = limit
