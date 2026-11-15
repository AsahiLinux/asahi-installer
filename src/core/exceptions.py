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
