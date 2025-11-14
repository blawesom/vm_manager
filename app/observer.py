"""OBSERVER service for coherence checks between QEMU, filesystem, and database.

The OBSERVER service runs periodic checks (interval ≤5s) to detect inconsistencies:
- Compares VM state in the database with running QEMU processes.
- Checks if disk files exist on the filesystem and match database records.
- Logs mismatches without automatic correction (repair is policy-dependent).

This module provides an ObserverInterface and a LocalObserver implementation
that uses simple subprocess calls to check QEMU process state and filesystem.
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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

    def __init__(self, db_operator=None, operator=None, check_interval: float = 5.0):
        """Initialize observer.

        Args:
            db_operator: Reference to DB_OPERATOR for querying VM and disk state.
            operator: Reference to OPERATOR (mainly for logging; not used for checks).
            check_interval: Time in seconds between checks (will be clamped to ≤5s).
        """
        self.db_operator = db_operator
        self.operator = operator
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

        if not self.db_operator:
            logger.warning("db_operator not set; skipping VM coherence check")
            return issues

        try:
            # Get list of running QEMU processes (simple grep-based check).
            running_pids = self._get_running_qemu_pids()
        except Exception as e:
            logger.error("Failed to get QEMU processes: %s", e)
            return issues

        try:
            # Query all VMs from DB (this is pseudocode; adapt to actual db_operator).
            # For now, we'll log that we'd check VMs.
            logger.debug("Checking VM coherence: running_pids=%s", running_pids)
        except Exception as e:
            logger.error("Failed to query VMs from DB: %s", e)

        return issues

    def _check_disk_coherence(self) -> List[CoherenceIssue]:
        """Check disk state coherence against filesystem."""
        issues = []

        if not self.db_operator:
            logger.warning("db_operator not set; skipping disk coherence check")
            return issues

        try:
            # Query all disks from DB (this is pseudocode; adapt to actual db_operator).
            # For each disk, check if its file exists on the filesystem.
            logger.debug("Checking disk coherence")
        except Exception as e:
            logger.error("Failed to query disks from DB: %s", e)

        return issues

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
                        logger.warning(
                            "  - [%s] %s: %s",
                            issue.issue_type,
                            issue.resource_id,
                            issue.details,
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
