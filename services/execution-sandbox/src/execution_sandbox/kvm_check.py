"""KVM availability detection for Firecracker executor."""

from __future__ import annotations

import os
import stat

from architect_common.logging import get_logger

logger = get_logger(component="kvm_check")


def is_kvm_available() -> bool:
    """Check if /dev/kvm exists and is accessible.

    Firecracker requires KVM for hardware-accelerated virtualization.
    Returns ``False`` on any platform that doesn't support it.
    """
    kvm_path = "/dev/kvm"
    try:
        if not os.path.exists(kvm_path):
            logger.info("kvm_not_found", path=kvm_path)
            return False

        st = os.stat(kvm_path)
        if not stat.S_ISCHR(st.st_mode):
            logger.info("kvm_not_char_device", path=kvm_path)
            return False

        # Check we have read-write access
        if os.access(kvm_path, os.R_OK | os.W_OK):
            logger.info("kvm_available", path=kvm_path)
            return True

        logger.info("kvm_no_permission", path=kvm_path)
        return False
    except OSError as exc:
        logger.info("kvm_check_error", path=kvm_path, error=str(exc))
        return False


def is_firecracker_available(binary_path: str = "/usr/bin/firecracker") -> bool:
    """Check if the Firecracker binary exists and is executable."""
    try:
        return os.path.isfile(binary_path) and os.access(binary_path, os.X_OK)
    except OSError:
        return False
