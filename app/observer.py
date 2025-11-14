"""OBSERVER service for coherence checks between QEMU, filesystem, and database.

The OBSERVER service runs periodic checks (interval ≤5s) to detect inconsistencies:
- Compares VM state in the database with running QEMU processes.
- Checks if disk files exist on the filesystem and match database records.
- Logs mismatches without automatic correction (repair is policy-dependent).

This module provides an ObserverInterface and a LocalObserver implementation
that uses simple subprocess calls to check QEMU process state and filesystem.
"""
from __future__ import annotations

import subprocess
import threading
import time
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Callable
from dataclasses import dataclass

from . import logging_config

logger = logging_config.UnifiedLogger.get_logger(__name__, logging_config.UnifiedLogger.SERVICE_OBSERVER)


@dataclass
class CoherenceIssue:
    """Represents a detected data coherence problem."""
    issue_type: str  # "vm_state_mismatch", "missing_disk", "orphan_process", etc.
    resource_id: str
    details: str


class ObserverInterface(ABC):
    """Abstract interface for the OBSERVER service."""

    @abstractmethod
    def check_coherence(self) -> List[CoherenceIssue]:
        """Perform coherence checks and return list of issues found."""

    @abstractmethod
    def start(self) -> None:
        """Start the observer background task."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the observer background task."""


class LocalObserver(ObserverInterface):
    """Local observer implementation for coherence checks.

    Runs a background thread that periodically (interval ≤5s) checks:
    - Whether DB VMs have corresponding running QEMU processes.
    - Whether DB disks have corresponding files on the filesystem.
    - Orphan QEMU processes or disk files not in the database.
    """

    def __init__(self, db_session_factory: Optional[Callable] = None, operator=None, 
                 storage_path: Optional[Path] = None, check_interval: float = 5.0):
        """Initialize observer.

        Args:
            db_session_factory: Callable that returns a DB session (e.g., SessionLocal).
            operator: Reference to OPERATOR for storage path and VM process checks.
            storage_path: Base storage path for VMs and disks (from operator if not provided).
            check_interval: Time in seconds between checks (will be clamped to ≤5s).
        """
        self.db_session_factory = db_session_factory
        self.operator = operator
        self.storage_path = Path(storage_path) if storage_path else (
            Path(operator.storage_path) if operator else Path(os.environ.get("VMAN_STORAGE_PATH", "/var/lib/vman"))
        )
        self.check_interval = min(float(check_interval), 5.0)
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_issues: List[CoherenceIssue] = []

    def check_coherence(self) -> List[CoherenceIssue]:
        """Run all coherence checks and return issues."""
        issues = []

        # Check VMs: compare DB state with running QEMU processes.
        issues.extend(self._check_vm_coherence())

        # Check disks: compare DB state with filesystem.
        issues.extend(self._check_disk_coherence())

        self.last_issues = issues
        return issues

    def _check_vm_coherence(self) -> List[CoherenceIssue]:
        """Check VM state coherence against QEMU processes."""
        issues = []

        if not self.db_session_factory:
            logger.warning("db_session_factory not set; skipping VM coherence check")
            return issues

        try:
            # Get list of running QEMU processes
            running_pids = self._get_running_qemu_pids()
            # Get VM IDs from PID files
            running_vm_ids = self._get_vm_ids_from_pid_files()
        except Exception as e:
            logger.error("Failed to get QEMU processes: %s", e)
            return issues

        try:
            # Import here to avoid circular imports
            from . import models
            
            # Query all VMs from DB
            db_session = self.db_session_factory()
            try:
                db_vms = db_session.query(models.VM).all()
                
                # Check each DB VM
                for vm in db_vms:
                    vm_running = vm.id in running_vm_ids
                    
                    if vm.state == "running" and not vm_running:
                        # DB says running but process not found
                        issues.append(CoherenceIssue(
                            issue_type="vm_state_mismatch",
                            resource_id=vm.id,
                            details=f"DB state is 'running' but QEMU process not found"
                        ))
                    elif vm.state != "running" and vm_running:
                        # DB says stopped but process is running
                        issues.append(CoherenceIssue(
                            issue_type="vm_state_mismatch",
                            resource_id=vm.id,
                            details=f"DB state is '{vm.state}' but QEMU process is running"
                        ))
                
                # Check for orphan processes (running but not in DB)
                db_vm_ids = {vm.id for vm in db_vms}
                for vm_id in running_vm_ids:
                    if vm_id not in db_vm_ids:
                        issues.append(CoherenceIssue(
                            issue_type="orphan_process",
                            resource_id=vm_id,
                            details="QEMU process running but VM not found in database"
                        ))
            finally:
                db_session.close()
        except Exception as e:
            logger.error("Failed to query VMs from DB: %s", e)

        return issues

    def _check_disk_coherence(self) -> List[CoherenceIssue]:
        """Check disk state coherence against filesystem."""
        issues = []

        if not self.db_session_factory:
            logger.warning("db_session_factory not set; skipping disk coherence check")
            return issues

        try:
            # Import here to avoid circular imports
            from . import models
            
            # Query all disks from DB
            db_session = self.db_session_factory()
            try:
                db_disks = db_session.query(models.Disk).all()
                
                # Check each DB disk
                for disk in db_disks:
                    disk_path = self.storage_path / "disks" / f"{disk.id}.qcow2"
                    
                    if not disk_path.exists():
                        # DB has disk record but file doesn't exist
                        issues.append(CoherenceIssue(
                            issue_type="missing_disk",
                            resource_id=disk.id,
                            details=f"Disk file not found: {disk_path}"
                        ))
                    elif disk.state == "attached" and not disk.vm_id:
                        # Disk marked as attached but no VM ID
                        issues.append(CoherenceIssue(
                            issue_type="disk_state_inconsistent",
                            resource_id=disk.id,
                            details="Disk state is 'attached' but vm_id is None"
                        ))
                    elif disk.state == "available" and disk.vm_id:
                        # Disk marked as available but has VM ID
                        issues.append(CoherenceIssue(
                            issue_type="disk_state_inconsistent",
                            resource_id=disk.id,
                            details=f"Disk state is 'available' but attached to VM {disk.vm_id}"
                        ))
                
                # Check for orphan disk files (exist but not in DB)
                disks_dir = self.storage_path / "disks"
                if disks_dir.exists():
                    db_disk_ids = {disk.id for disk in db_disks}
                    for disk_file in disks_dir.glob("*.qcow2"):
                        disk_id = disk_file.stem  # filename without .qcow2
                        if disk_id not in db_disk_ids:
                            issues.append(CoherenceIssue(
                                issue_type="orphan_disk",
                                resource_id=disk_id,
                                details=f"Disk file exists but not found in database: {disk_file}"
                            ))
            finally:
                db_session.close()
        except Exception as e:
            logger.error("Failed to query disks from DB: %s", e)

        return issues

    def _get_vm_ids_from_pid_files(self) -> List[str]:
        """Get list of VM IDs from PID files in storage directory.
        
        Returns:
            List of VM IDs that have PID files (indicating they should be running).
        """
        vm_ids = []
        vms_dir = self.storage_path / "vms"
        
        if not vms_dir.exists():
            return vm_ids
        
        for vm_dir in vms_dir.iterdir():
            if vm_dir.is_dir():
                pid_file = vm_dir / "qemu.pid"
                if pid_file.exists():
                    # Check if process is actually running
                    try:
                        pid = int(pid_file.read_text().strip())
                        os.kill(pid, 0)  # Signal 0 checks if process exists
                        vm_ids.append(vm_dir.name)
                    except (ValueError, OSError, ProcessLookupError):
                        # PID file exists but process is dead - this will be caught by VM coherence check
                        pass
        
        return vm_ids
    
    def _get_running_qemu_pids(self) -> List[int]:
        """Get list of running QEMU process IDs using pgrep or ps.

        Returns:
            List of QEMU process IDs, or empty list on error.
        """
        try:
            # Try pgrep first (faster and more portable).
            result = subprocess.run(
                ["pgrep", "-f", "qemu"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return [int(pid) for pid in result.stdout.strip().split("\n") if pid]
            return []
        except FileNotFoundError:
            logger.debug("pgrep not available; trying ps")
        except Exception as e:
            logger.error("Error running pgrep: %s", e)
            return []

        # Fallback: use ps (less efficient but more portable).
        try:
            result = subprocess.run(
                ["ps", "aux"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            )
            pids = []
            for line in result.stdout.split("\n"):
                if "qemu" in line.lower():
                    parts = line.split()
                    if len(parts) > 1:
                        try:
                            pids.append(int(parts[1]))
                        except ValueError:
                            pass
            return pids
        except Exception as e:
            logger.error("Error running ps: %s", e)
            return []

    def _observer_loop(self) -> None:
        """Background thread loop for periodic coherence checks."""
        logger.info("Observer loop starting (check_interval=%.1fs)", self.check_interval)
        while self.running:
            try:
                issues = self.check_coherence()
                if issues:
                    logger.warning("Coherence check found %d issue(s)", len(issues))
                    for issue in issues:
                        logging_config.UnifiedLogger.log_coherence_issue(
                            logger, issue.issue_type, issue.resource_id, issue.details
                        )
                else:
                    logger.debug("Coherence check passed")
            except Exception as e:
                logger.error("Error in observer loop: %s", e)

            # Sleep for the check interval, but allow for quick stop.
            for _ in range(int(self.check_interval * 10)):
                if not self.running:
                    break
                time.sleep(0.1)

    def start(self) -> None:
        """Start the observer background thread."""
        if self.running:
            logger.warning("Observer already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._observer_loop, daemon=True)
        self.thread.start()
        logger.info("Observer started")

    def stop(self) -> None:
        """Stop the observer background thread."""
        if not self.running:
            logger.warning("Observer not running")
            return

        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
            logger.info("Observer stopped")
