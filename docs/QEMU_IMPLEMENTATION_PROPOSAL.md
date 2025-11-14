# QEMU Interactions Implementation Proposal

## Overview

This document proposes the implementation of QEMU interactions for the OPERATOR service (step 2/3 of the development plan). The implementation will enable full VM lifecycle management and disk hot-plugging capabilities.

## Architecture

### Components

1. **Process Management**: Track QEMU VM processes using PID files
2. **QEMU Command Execution**: Use `qemu-system-x86_64` (or architecture-specific) for VM lifecycle
3. **QMP (QEMU Monitor Protocol)**: For advanced operations like hot-plugging disks
4. **Storage Management**: Coordinate with existing disk image operations

### Directory Structure

```
/storage/
  ├── vms/
  │   ├── {vm_id}/
  │   │   ├── root.qcow2          # Root disk (if created with VM)
  │   │   ├── qemu.pid            # QEMU process PID
  │   │   ├── qmp.sock            # QMP socket for this VM
  │   │   └── qemu.log            # QEMU stdout/stderr log
  │   └── ...
  └── disks/
      ├── {disk_id}.qcow2
      └── ...
```

## Implementation Details

### 1. VM Process Tracking

**Strategy**: Use PID files stored in VM-specific directories to track running instances.

```python
def _get_vm_pid_file(self, vm_id: str) -> Path:
    """Get path to PID file for a VM."""
    storage_base = Path(os.environ.get("VMAN_STORAGE_PATH", "/var/lib/vman"))
    return storage_base / "vms" / vm_id / "qemu.pid"

def _is_vm_running(self, vm_id: str) -> bool:
    """Check if VM is running by verifying PID file and process."""
    pid_file = self._get_vm_pid_file(vm_id)
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        # Check if process exists
        os.kill(pid, 0)  # Signal 0 doesn't kill, just checks existence
        return True
    except (ValueError, OSError, ProcessLookupError):
        # PID file exists but process is dead - clean up
        pid_file.unlink(missing_ok=True)
        return False
```

### 2. Start VM (`start_vm`)

**Implementation**:
- Build QEMU command with appropriate parameters from VM template
- Create VM directory structure
- Launch QEMU as background process
- Store PID and create QMP socket
- Configure networking (user-mode or bridge)

```python
def start_vm(self, vm_id: str, qcow2_path: Optional[Path] = None, 
             cpu_count: int = 1, ram_gb: int = 1) -> None:
    """Start a VM with specified resources."""
    if self._is_vm_running(vm_id):
        raise OperatorError(f"VM {vm_id} is already running")
    
    # Determine QEMU binary
    qemu_bin = shutil.which("qemu-system-x86_64") or shutil.which("qemu-kvm")
    if not qemu_bin:
        raise OperatorError("qemu-system-x86_64 or qemu-kvm not found")
    
    # Setup VM directory
    vm_dir = self._get_vm_dir(vm_id)
    vm_dir.mkdir(parents=True, exist_ok=True)
    
    # QMP socket path
    qmp_sock = vm_dir / "qmp.sock"
    
    # Root disk (create if not provided)
    if qcow2_path is None:
        qcow2_path = vm_dir / "root.qcow2"
        if not qcow2_path.exists():
            # Create minimal root disk (10GB default)
            self.create_disk_image(qcow2_path, size_gb=10)
    
    # Build QEMU command
    cmd = [
        qemu_bin,
        "-name", vm_id,
        "-machine", "type=q35,accel=kvm:tcg",
        "-cpu", "host",
        "-smp", str(cpu_count),
        "-m", f"{ram_gb}G",
        "-drive", f"file={qcow2_path},format=qcow2,if=virtio,id=drive0",
        "-netdev", "user,id=net0,hostfwd=tcp::0-:22",
        "-device", "virtio-net,netdev=net0",
        "-monitor", f"unix:{qmp_sock},server,nowait",
        "-daemonize",
        "-pidfile", str(vm_dir / "qemu.pid"),
        "-no-reboot",
    ]
    
    # Execute
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            raise OperatorError(f"QEMU start failed: {result.stderr}")
        
        # Verify VM started
        if not self._is_vm_running(vm_id):
            raise OperatorError("VM process not found after start")
            
    except subprocess.TimeoutExpired:
        raise OperatorError("QEMU start timed out")
    except Exception as e:
        raise OperatorError(f"Failed to start VM: {e}")
```

### 3. Stop VM (`stop_vm`)

**Implementation**:
- Attempt graceful shutdown via QMP (ACPI shutdown)
- Fallback to SIGTERM if QMP unavailable
- Force kill (SIGKILL) as last resort
- Clean up PID file and sockets

```python
def stop_vm(self, vm_id: str, force: bool = False) -> None:
    """Stop a VM gracefully or forcefully."""
    if not self._is_vm_running(vm_id):
        logger.warning(f"VM {vm_id} is not running")
        return
    
    pid_file = self._get_vm_pid_file(vm_id)
    pid = int(pid_file.read_text().strip())
    vm_dir = self._get_vm_dir(vm_id)
    qmp_sock = vm_dir / "qmp.sock"
    
    if not force:
        # Try graceful shutdown via QMP
        try:
            self._qmp_command(qmp_sock, {"execute": "system_powerdown"})
            # Wait up to 30 seconds for graceful shutdown
            for _ in range(30):
                time.sleep(1)
                if not self._is_vm_running(vm_id):
                    return
        except Exception as e:
            logger.warning(f"QMP shutdown failed: {e}, trying SIGTERM")
    
    # Send SIGTERM
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            time.sleep(1)
            if not self._is_vm_running(vm_id):
                return
    except ProcessLookupError:
        return  # Already stopped
    
    # Force kill if still running
    if force or self._is_vm_running(vm_id):
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)
        except ProcessLookupError:
            pass
    
    # Cleanup
    pid_file.unlink(missing_ok=True)
    qmp_sock.unlink(missing_ok=True)
```

### 4. Attach Disk (`attach_disk`)

**Implementation**:
- Use QMP to hot-plug disk to running VM
- Map device name to QEMU drive/device IDs
- Support virtio-blk for better performance

```python
def attach_disk(self, vm_id: str, disk_path: Path, device: str = "/dev/xvda") -> None:
    """Attach a disk to a running VM using QMP hot-plug."""
    if not self._is_vm_running(vm_id):
        raise OperatorError(f"VM {vm_id} is not running")
    
    if not disk_path.exists():
        raise OperatorError(f"Disk image not found: {disk_path}")
    
    # Map device name to drive ID (e.g., /dev/xvdb -> drive1)
    device_map = {
        "/dev/xvda": "drive0",
        "/dev/xvdb": "drive1",
        "/dev/xvdc": "drive2",
        "/dev/xvdd": "drive3",
    }
    drive_id = device_map.get(device, f"drive_{device.replace('/', '_')}")
    
    vm_dir = self._get_vm_dir(vm_id)
    qmp_sock = vm_dir / "qmp.sock"
    
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
```

### 5. Detach Disk (`detach_disk`)

**Implementation**:
- Use QMP to hot-unplug disk from running VM
- Remove device first, then blockdev

```python
def detach_disk(self, vm_id: str, disk_path: Path) -> None:
    """Detach a disk from a running VM using QMP hot-unplug."""
    if not self._is_vm_running(vm_id):
        raise OperatorError(f"VM {vm_id} is not running")
    
    vm_dir = self._get_vm_dir(vm_id)
    qmp_sock = vm_dir / "qmp.sock"
    
    # Find device ID by querying block devices
    block_info = self._qmp_command(qmp_sock, {"execute": "query-block"})
    
    # Find the device using this disk path
    device_id = None
    for device in block_info.get("return", []):
        if device.get("inserted", {}).get("file") == str(disk_path):
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
```

### 6. QMP Helper Functions

**Implementation**:
- Socket-based communication with QEMU monitor
- JSON protocol handling
- Error handling and retries

```python
def _qmp_command(self, qmp_sock: Path, command: dict, timeout: float = 5.0) -> dict:
    """Send a QMP command to QEMU monitor socket."""
    import socket
    import json
    
    if not qmp_sock.exists():
        raise OperatorError(f"QMP socket not found: {qmp_sock}")
    
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(str(qmp_sock))
        
        # QMP handshake
        greeting = json.loads(sock.recv(1024).decode())
        if "QMP" not in greeting:
            raise OperatorError("Invalid QMP greeting")
        
        # Enable QMP
        sock.send(json.dumps({"execute": "qmp_capabilities"}).encode() + b"\n")
        response = json.loads(sock.recv(1024).decode())
        if "error" in response:
            raise OperatorError(f"QMP capabilities failed: {response['error']}")
        
        # Send command
        sock.send(json.dumps(command).encode() + b"\n")
        response = json.loads(sock.recv(4096).decode())
        
        if "error" in response:
            raise OperatorError(f"QMP command failed: {response['error']}")
        
        return response
        
    except socket.timeout:
        raise OperatorError("QMP command timed out")
    except Exception as e:
        raise OperatorError(f"QMP communication failed: {e}")
    finally:
        sock.close()
```

## Configuration

### Environment Variables

- `VMAN_STORAGE_PATH`: Base directory for VM and disk storage (default: `/var/lib/vman`)
- `VMAN_OPERATOR_DRY_RUN`: Enable dry-run mode (default: `0`)
- `VMAN_QEMU_BINARY`: Override QEMU binary path (default: auto-detect)

### Required System Dependencies

- `qemu-system-x86_64` or `qemu-kvm`
- `qemu-img` (already used)
- Python `socket` module (standard library)
- Appropriate permissions for:
  - Creating/removing files in storage directory
  - Executing QEMU
  - Creating network interfaces (may require root or capabilities)

## Error Handling

All methods should:
1. Validate inputs (VM exists, disk exists, etc.)
2. Check VM state before operations
3. Provide clear error messages via `OperatorError`
4. Clean up resources on failure (where possible)
5. Log operations at appropriate levels

## Testing Considerations

1. **Unit Tests**: Mock subprocess and socket operations
2. **Integration Tests**: Require QEMU installed, use test storage directory
3. **Dry-Run Mode**: Already implemented, should work with new methods
4. **Process Isolation**: Each test should use unique VM IDs

## Security Considerations

1. **Path Validation**: Ensure disk paths are within storage directory
2. **Process Isolation**: VMs should run with appropriate user/group
3. **Network Isolation**: Consider using bridge networking with proper firewall rules
4. **Resource Limits**: Consider cgroups for CPU/memory limits

## Migration Path

1. Implement helper methods first (`_get_vm_dir`, `_is_vm_running`, `_qmp_command`)
2. Implement `start_vm` with basic functionality
3. Implement `stop_vm` with graceful shutdown
4. Implement `attach_disk` and `detach_disk` using QMP
5. Add comprehensive error handling and logging
6. Add integration tests

## Future Enhancements

1. **VM State Querying**: Add method to query VM state via QMP
2. **Network Configuration**: Support for bridge networking, static IPs
3. **Resource Monitoring**: CPU/memory usage via QMP
4. **Snapshot Management**: QCOW2 snapshot operations
5. **Migration Support**: Live migration between hosts

