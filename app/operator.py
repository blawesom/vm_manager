"""OPERATOR interfaces for QEMU and filesystem interactions.

This module defines an abstract OperatorInterface and a LocalOperator implementation
that provides safe, testable stubs for disk and VM operations. The LocalOperator
uses subprocess to call qemu-img for disk creation/deletion when available, and
performs filesystem operations using pathlib.

Implementations should be provided by the local environment (e.g. a real
operator that talks to QEMU and the host filesystem). The provided LocalOperator
is intentionally conservative: it checks for required binaries and either
executes them or raises a RuntimeError. VM lifecycle operations are left as
stubs because full VM lifecycle management involves more environment-specific
details.
"""
from __future__ import annotations

import subprocess
import shutil
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class OperatorError(RuntimeError):
    pass


class OperatorInterface(ABC):
    """Abstract interface for OPERATOR responsibilities.

    Implementations must be safe to call from the INTEL service and should
    raise OperatorError on failure.
    """

    @abstractmethod
    def create_disk_image(self, path: Path, size_gb: int, fmt: str = "qcow2") -> Path:
        """Create a disk image at `path` with size `size_gb` (GB).

        Returns the path to the created image on success, or raises OperatorError.
        """

    @abstractmethod
    def delete_disk_image(self, path: Path) -> None:
        """Delete a disk image file at `path`.

        Should raise OperatorError on failure.
        """

    @abstractmethod
    def ensure_storage_dir(self, path: Path) -> Path:
        """Ensure the parent directory for a disk or VM exists and is writable.

        Returns the directory path.
        """

    @abstractmethod
    def attach_disk(self, vm_id: str, disk_path: Path, device: str = "/dev/xvda") -> None:
        """Attach a disk to a VM. Implementation-specific; may raise OperatorError.
        """

    @abstractmethod
    def detach_disk(self, vm_id: str, disk_path: Path) -> None:
        """Detach a disk from a VM. Implementation-specific; may raise OperatorError.
        """

    @abstractmethod
    def start_vm(self, vm_id: str, qcow2_path: Optional[Path] = None) -> None:
        """Start a VM identified by vm_id. Optional qcow2_path for root disk."""

    @abstractmethod
    def stop_vm(self, vm_id: str) -> None:
        """Stop a VM identified by vm_id."""


class LocalOperator(OperatorInterface):
    """Local operator implementation with conservative behavior.

    - `qemu-img` is used for disk image creation if available.
    - Filesystem operations use pathlib and os.
    - VM lifecycle methods are left as placeholders and should be implemented
      by a more capable provider when running on a system with QEMU and a
      process supervisor.
    """

    def __init__(self, dry_run: bool = False):
        self.qemu_img = shutil.which("qemu-img")
        self.dry_run = bool(dry_run or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1")
        logger.debug("LocalOperator init: qemu-img=%s dry_run=%s", self.qemu_img, self.dry_run)

    def create_disk_image(self, path: Path, size_gb: int, fmt: str = "qcow2") -> Path:
        path = Path(path)
        self.ensure_storage_dir(path)
        if path.exists():
            raise OperatorError(f"Disk image already exists: {path}")

        if self.dry_run:
            logger.info("dry-run: would create disk %s size=%dG fmt=%s", path, size_gb, fmt)
            return path

        if not self.qemu_img:
            raise OperatorError("qemu-img not found in PATH; cannot create disk image")

        cmd = [self.qemu_img, "create", "-f", fmt, str(path), f"{size_gb}G"]
        logger.debug("Running: %s", " ".join(cmd))
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            logger.error("qemu-img failed: %s", e.stderr.decode(errors="ignore"))
            raise OperatorError(f"qemu-img failed: {e}")
        return path

    def delete_disk_image(self, path: Path) -> None:
        path = Path(path)
        if self.dry_run:
            logger.info("dry-run: would delete disk %s", path)
            return
        try:
            path.unlink()
        except FileNotFoundError:
            raise OperatorError(f"Disk image not found: {path}")
        except Exception as e:
            raise OperatorError(f"Failed to delete disk image {path}: {e}")

    def ensure_storage_dir(self, path: Path) -> Path:
        d = path.parent
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise OperatorError(f"Failed to create storage directory {d}: {e}")
        if not os.access(d, os.W_OK):
            raise OperatorError(f"Storage directory not writable: {d}")
        return d

    def attach_disk(self, vm_id: str, disk_path: Path, device: str = "/dev/xvda") -> None:
        # Attaching a disk to a running VM depends on the hypervisor and qemu monitor
        # interface. This is left as a placeholder; an implementation may use
        # libvirt, QMP (QEMU Machine Protocol), or guest-agent commands.
        logger.info("attach_disk called vm_id=%s disk=%s device=%s (stub)", vm_id, disk_path, device)
        if self.dry_run:
            return
        raise OperatorError("attach_disk not implemented in LocalOperator")

    def detach_disk(self, vm_id: str, disk_path: Path) -> None:
        logger.info("detach_disk called vm_id=%s disk=%s (stub)", vm_id, disk_path)
        if self.dry_run:
            return
        raise OperatorError("detach_disk not implemented in LocalOperator")

    def start_vm(self, vm_id: str, qcow2_path: Optional[Path] = None) -> None:
        logger.info("start_vm called vm_id=%s qcow2=%s (stub)", vm_id, qcow2_path)
        if self.dry_run:
            return
        raise OperatorError("start_vm not implemented in LocalOperator")

    def stop_vm(self, vm_id: str) -> None:
        logger.info("stop_vm called vm_id=%s (stub)", vm_id)
        if self.dry_run:
            return
        raise OperatorError("stop_vm not implemented in LocalOperator")
