"""OPERATOR interfaces for QEMU and filesystem interactions.

This module defines an abstract OperatorInterface and a LocalOperator implementation
that provides QEMU VM lifecycle management and disk operations. The LocalOperator
uses subprocess to call qemu-img for disk creation/deletion and qemu-system-x86_64
for VM management, with QMP (QEMU Monitor Protocol) for advanced operations like
hot-plugging disks.
"""
from __future__ import annotations

import subprocess
import shutil
import os
import signal
import socket
import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from . import logging_config

logger = logging_config.UnifiedLogger.get_logger(__name__, logging_config.UnifiedLogger.SERVICE_OPERATOR)

# Network manager will be imported when needed to avoid circular imports


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
    """Local operator implementation with full QEMU support.

    - `qemu-img` is used for disk image creation if available.
    - `qemu-system-x86_64` or `qemu-kvm` is used for VM lifecycle management.
    - QMP (QEMU Monitor Protocol) is used for hot-plugging disks.
    - Filesystem operations use pathlib and os.
    """

    def __init__(self, dry_run: bool = False, storage_path: Optional[Path] = None, network_manager=None):
        self.qemu_img = shutil.which("qemu-img")
        self.qemu_bin = shutil.which("qemu-system-x86_64") or shutil.which("qemu-kvm")
        self.dry_run = bool(dry_run or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1")
        self.storage_path = Path(storage_path or os.environ.get("VMAN_STORAGE_PATH", "/var/lib/vman"))
        self.network_manager = network_manager
        logger.debug("LocalOperator init: qemu-img=%s qemu-bin=%s storage=%s dry_run=%s network=%s",
                    self.qemu_img, self.qemu_bin, self.storage_path, self.dry_run,
                    "enabled" if network_manager else "disabled")
    
    def _get_vm_dir(self, vm_id: str) -> Path:
        """Get VM-specific directory."""
        return self.storage_path / "vms" / vm_id
    
    def _get_vm_pid_file(self, vm_id: str) -> Path:
        """Get path to PID file for a VM."""
        return self._get_vm_dir(vm_id) / "qemu.pid"
    
    def _get_vm_qmp_socket(self, vm_id: str) -> Path:
        """Get path to QMP socket for a VM."""
        return self._get_vm_dir(vm_id) / "qmp.sock"
    
    def _is_vm_running(self, vm_id: str) -> bool:
        """Check if VM is running by verifying PID file and process."""
        pid_file = self._get_vm_pid_file(vm_id)
        if not pid_file.exists():
            return False
        try:
            pid = int(pid_file.read_text().strip())
            # Signal 0 doesn't kill, just checks existence
            os.kill(pid, 0)
            return True
        except (ValueError, OSError, ProcessLookupError):
            # PID file exists but process is dead - clean up
            pid_file.unlink(missing_ok=True)
            return False
    
    def _qmp_command(self, qmp_sock: Path, command: dict, timeout: float = 5.0) -> dict:
        """Send a QMP command to QEMU monitor socket."""
        if not qmp_sock.exists():
            raise OperatorError(f"QMP socket not found: {qmp_sock}")
        
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(timeout)
            sock.connect(str(qmp_sock))
            
            # QMP handshake
            greeting_data = b""
            while b"\n" not in greeting_data:
                greeting_data += sock.recv(1024)
            greeting = json.loads(greeting_data.decode())
            if "QMP" not in greeting:
                raise OperatorError("Invalid QMP greeting")
            
            # Enable QMP
            sock.send(json.dumps({"execute": "qmp_capabilities"}).encode() + b"\n")
            response_data = b""
            while b"\n" not in response_data:
                response_data += sock.recv(1024)
            response = json.loads(response_data.decode())
            if "error" in response:
                raise OperatorError(f"QMP capabilities failed: {response['error']}")
            
            # Send command
            sock.send(json.dumps(command).encode() + b"\n")
            response_data = b""
            while b"\n" not in response_data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
            response = json.loads(response_data.decode())
            
            if "error" in response:
                raise OperatorError(f"QMP command failed: {response['error']}")
            
            return response
            
        except socket.timeout:
            raise OperatorError("QMP command timed out")
        except json.JSONDecodeError as e:
            raise OperatorError(f"Invalid QMP response: {e}")
        except Exception as e:
            raise OperatorError(f"QMP communication failed: {e}")
        finally:
            sock.close()

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

    def start_vm(self, vm_id: str, qcow2_path: Optional[Path] = None,
                 cpu_count: int = 1, ram_gb: int = 1) -> None:
        """Start a VM with specified resources."""
        if self.dry_run:
            logger.info("dry-run: would start VM %s cpu=%d ram=%dG", vm_id, cpu_count, ram_gb)
            return
        
        if self._is_vm_running(vm_id):
            raise OperatorError(f"VM {vm_id} is already running")
        
        if not self.qemu_bin:
            raise OperatorError("qemu-system-x86_64 or qemu-kvm not found in PATH")
        
        # Setup VM directory
        vm_dir = self._get_vm_dir(vm_id)
        vm_dir.mkdir(parents=True, exist_ok=True)
        
        # QMP socket path
        qmp_sock = self._get_vm_qmp_socket(vm_id)
        if qmp_sock.exists():
            qmp_sock.unlink()  # Clean up stale socket
        
        # Root disk (create if not provided)
        if qcow2_path is None:
            qcow2_path = vm_dir / "root.qcow2"
            if not qcow2_path.exists():
                # Create minimal root disk (10GB default)
                if not self.qemu_img:
                    raise OperatorError("qemu-img not found; cannot create root disk")
                cmd = [self.qemu_img, "create", "-f", "qcow2", str(qcow2_path), "10G"]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if not qcow2_path.exists():
            raise OperatorError(f"Root disk not found: {qcow2_path}")
        
        # Build QEMU command
        pid_file = self._get_vm_pid_file(vm_id)
        log_file = vm_dir / "qemu.log"
        
        # Network configuration
        tap_name = None
        vm_ip = None
        if self.network_manager and not self.dry_run:
            try:
                # Check if VM had a previous IP assignment
                ip_file = vm_dir / "ip.txt"
                previous_ip = ip_file.read_text().strip() if ip_file.exists() else None
                
                # Ensure bridge exists
                self.network_manager.ensure_bridge()
                # Create TAP interface
                tap_name = self.network_manager.create_tap_interface(vm_id)
                
                # Allocate IP address (reuse previous if available and not allocated)
                if previous_ip and previous_ip not in self.network_manager.get_allocated_ips():
                    vm_ip = previous_ip
                    self.network_manager.allocated_ips.add(vm_ip)
                    logger.info(f"Reusing previous IP {vm_ip} for VM {vm_id}")
                else:
                    vm_ip = self.network_manager.allocate_ip(vm_id)
                
                # Store IP in VM directory for reference
                (vm_dir / "ip.txt").write_text(vm_ip)
                (vm_dir / "tap.txt").write_text(tap_name)
            except Exception as e:
                logger.warning(f"Failed to setup network for VM {vm_id}: {e}, falling back to user-mode")
                # Fall back to user-mode networking
                tap_name = None
                vm_ip = None
        
        # Build QEMU command
        cmd = [
            self.qemu_bin,
            "-name", vm_id,
            "-machine", "type=q35,accel=kvm:tcg",
            "-cpu", "host",
            "-smp", str(cpu_count),
            "-m", f"{ram_gb}G",
            "-drive", f"file={qcow2_path},format=qcow2,if=virtio,id=drive0",
            "-monitor", f"unix:{qmp_sock},server,nowait",
            "-daemonize",
            "-pidfile", str(pid_file),
            "-no-reboot",
            "-display", "none",
        ]
        
        # Add network configuration
        if tap_name:
            # Generate unique MAC address based on VM ID
            import hashlib
            mac_hash = hashlib.md5(vm_id.encode()).hexdigest()[:6]
            mac = f"52:54:{mac_hash[0:2]}:{mac_hash[2:4]}:{mac_hash[4:6]}:00"
            # Use TAP interface with bridge
            cmd.extend([
                "-netdev", f"tap,id=net0,ifname={tap_name},script=no,downscript=no",
                "-device", f"virtio-net,netdev=net0,mac={mac}"
            ])
        else:
            # Fall back to user-mode networking
            cmd.extend([
                "-netdev", "user,id=net0,hostfwd=tcp::0-:22",
                "-device", "virtio-net,netdev=net0"
            ])
        
        # Execute
        try:
            with open(log_file, "w") as log:
                result = subprocess.run(
                    cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=30
                )
            if result.returncode != 0:
                raise OperatorError(f"QEMU start failed (check {log_file})")
            
            # Wait a moment for VM to start
            time.sleep(1)
            
            # Verify VM started
            if not self._is_vm_running(vm_id):
                raise OperatorError("VM process not found after start")
            
            logger.info(f"Started VM {vm_id} (PID: {pid_file.read_text().strip()})")
            if vm_ip:
                logger.info(f"VM {vm_id} assigned IP: {vm_ip}")
            
        except subprocess.TimeoutExpired:
            # Cleanup network resources on failure
            if tap_name and self.network_manager:
                try:
                    self.network_manager.delete_tap_interface(tap_name)
                    if vm_ip:
                        self.network_manager.release_ip(vm_ip)
                except Exception:
                    pass
            raise OperatorError("QEMU start timed out")
        except Exception as e:
            # Cleanup network resources on failure
            if tap_name and self.network_manager:
                try:
                    self.network_manager.delete_tap_interface(tap_name)
                    if vm_ip:
                        self.network_manager.release_ip(vm_ip)
                except Exception:
                    pass
            raise OperatorError(f"Failed to start VM: {e}")

    def stop_vm(self, vm_id: str, force: bool = False) -> None:
        """Stop a VM gracefully or forcefully."""
        if self.dry_run:
            logger.info("dry-run: would stop VM %s (force=%s)", vm_id, force)
            return
        
        if not self._is_vm_running(vm_id):
            logger.warning(f"VM {vm_id} is not running")
            return
        
        pid_file = self._get_vm_pid_file(vm_id)
        pid = int(pid_file.read_text().strip())
        qmp_sock = self._get_vm_qmp_socket(vm_id)
        
        if not force:
            # Try graceful shutdown via QMP
            try:
                self._qmp_command(qmp_sock, {"execute": "system_powerdown"})
                # Wait up to 30 seconds for graceful shutdown
                for _ in range(30):
                    time.sleep(1)
                    if not self._is_vm_running(vm_id):
                        logger.info(f"VM {vm_id} stopped gracefully")
                        return
            except Exception as e:
                logger.warning(f"QMP shutdown failed: {e}, trying SIGTERM")
        
        # Send SIGTERM
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                time.sleep(1)
                if not self._is_vm_running(vm_id):
                    logger.info(f"VM {vm_id} stopped via SIGTERM")
                    return
        except ProcessLookupError:
            logger.info(f"VM {vm_id} already stopped")
            return
        
        # Force kill if still running
        if force or self._is_vm_running(vm_id):
            try:
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
                logger.info(f"VM {vm_id} force-killed")
            except ProcessLookupError:
                pass
        
        # Cleanup network resources
        if self.network_manager:
            vm_dir = self._get_vm_dir(vm_id)
            tap_file = vm_dir / "tap.txt"
            ip_file = vm_dir / "ip.txt"
            
            if tap_file.exists():
                tap_name = tap_file.read_text().strip()
                self.network_manager.delete_tap_interface(tap_name)
                tap_file.unlink(missing_ok=True)
            
            if ip_file.exists():
                vm_ip = ip_file.read_text().strip()
                self.network_manager.release_ip(vm_ip)
                ip_file.unlink(missing_ok=True)
        
        # Cleanup
        pid_file.unlink(missing_ok=True)
        qmp_sock.unlink(missing_ok=True)

    def attach_disk(self, vm_id: str, disk_path: Path, device: str = "/dev/xvda") -> None:
        """Attach a disk to a running VM using QMP hot-plug."""
        if self.dry_run:
            logger.info("dry-run: would attach disk %s to VM %s as %s", disk_path, vm_id, device)
            return
        
        if not self._is_vm_running(vm_id):
            raise OperatorError(f"VM {vm_id} is not running")
        
        disk_path = Path(disk_path)
        if not disk_path.exists():
            raise OperatorError(f"Disk image not found: {disk_path}")
        
        # Map device name to drive ID (e.g., /dev/xvdb -> drive1)
        # Note: drive0 is typically the root disk
        device_map = {
            "/dev/xvda": "drive0",
            "/dev/xvdb": "drive1",
            "/dev/xvdc": "drive2",
            "/dev/xvdd": "drive3",
        }
        drive_id = device_map.get(device, f"drive_{device.replace('/', '_')}")
        
        qmp_sock = self._get_vm_qmp_socket(vm_id)
        
        # Step 1: Add drive via blockdev-add
        blockdev_cmd = {
            "execute": "blockdev-add",
            "arguments": {
                "node-name": drive_id,
                "driver": "qcow2",
                "file": {
                    "driver": "file",
                    "filename": str(disk_path)
                }
            }
        }
        self._qmp_command(qmp_sock, blockdev_cmd)
        
        # Step 2: Add device via device_add
        device_cmd = {
            "execute": "device_add",
            "arguments": {
                "driver": "virtio-blk-pci",
                "drive": drive_id,
                "id": f"virtio-{drive_id}",
                "bus": "pcie.0"
            }
        }
        self._qmp_command(qmp_sock, device_cmd)
        
        logger.info(f"Attached disk {disk_path} to VM {vm_id} as {device}")

    def detach_disk(self, vm_id: str, disk_path: Path) -> None:
        """Detach a disk from a running VM using QMP hot-unplug."""
        if self.dry_run:
            logger.info("dry-run: would detach disk %s from VM %s", disk_path, vm_id)
            return
        
        if not self._is_vm_running(vm_id):
            raise OperatorError(f"VM {vm_id} is not running")
        
        disk_path = Path(disk_path)
        qmp_sock = self._get_vm_qmp_socket(vm_id)
        
        # Find device ID by querying block devices
        block_info = self._qmp_command(qmp_sock, {"execute": "query-block"})
        
        # Find the device using this disk path
        device_id = None
        for device in block_info.get("return", []):
            inserted = device.get("inserted", {})
            if inserted and inserted.get("file") == str(disk_path):
                device_id = device.get("device")
                break
        
        if not device_id:
            raise OperatorError(f"Disk {disk_path} not found attached to VM {vm_id}")
        
        # Step 1: Remove device
        device_del_cmd = {
            "execute": "device_del",
            "arguments": {
                "id": device_id
            }
        }
        self._qmp_command(qmp_sock, device_del_cmd)
        
        # Step 2: Wait for device removal to complete
        for _ in range(10):
            time.sleep(0.5)
            block_info = self._qmp_command(qmp_sock, {"execute": "query-block"})
            if not any(d.get("device") == device_id for d in block_info.get("return", [])):
                break
        
        logger.info(f"Detached disk {disk_path} from VM {vm_id}")
