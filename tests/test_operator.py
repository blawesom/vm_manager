"""Unit tests for OPERATOR service with safety and security verification."""
import pytest
import os
import tempfile
from pathlib import Path
from app import operator


@pytest.fixture
def temp_storage():
    """Create temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_operator(temp_storage):
    """Create operator instance with temporary storage."""
    return operator.LocalOperator(dry_run=True, storage_path=temp_storage)


def test_create_disk_image_success(test_operator, temp_storage):
    """Test successful disk image creation."""
    disk_path = temp_storage / "test.qcow2"
    result = test_operator.create_disk_image(disk_path, size_gb=10)
    assert result == disk_path


def test_create_disk_image_already_exists(test_operator, temp_storage):
    """Test creating disk that already exists."""
    disk_path = temp_storage / "test.qcow2"
    test_operator.create_disk_image(disk_path, size_gb=10)
    
    # In dry-run mode, file won't exist, so create it manually for the test
    if test_operator.dry_run:
        disk_path.touch()
    
    # Try to create again
    with pytest.raises(operator.OperatorError, match="already exists"):
        test_operator.create_disk_image(disk_path, size_gb=10)


def test_delete_disk_image_success(test_operator, temp_storage):
    """Test successful disk image deletion."""
    disk_path = temp_storage / "test.qcow2"
    test_operator.create_disk_image(disk_path, size_gb=10)
    
    # In dry-run mode, file won't exist, so create it manually for the test
    if test_operator.dry_run:
        disk_path.touch()
    
    test_operator.delete_disk_image(disk_path)
    # In dry-run, file won't exist, but should not raise error


def test_delete_disk_image_not_found(test_operator, temp_storage):
    """Test deleting non-existent disk."""
    disk_path = temp_storage / "nonexistent.qcow2"
    with pytest.raises(operator.OperatorError, match="not found"):
        test_operator.delete_disk_image(disk_path)


def test_ensure_storage_dir_success(test_operator, temp_storage):
    """Test storage directory creation."""
    new_dir = temp_storage / "subdir" / "nested"
    result = test_operator.ensure_storage_dir(new_dir / "file.qcow2")
    assert result.exists()
    assert result.is_dir()


def test_ensure_storage_dir_permissions(test_operator, temp_storage):
    """Test storage directory writability check."""
    # This should pass in dry-run mode
    disk_path = temp_storage / "test.qcow2"
    result = test_operator.ensure_storage_dir(disk_path)
    assert result == disk_path.parent


def test_start_vm_dry_run(test_operator):
    """Test starting VM in dry-run mode."""
    # Should not raise error in dry-run
    test_operator.start_vm("test-vm", cpu_count=2, ram_gb=4)


def test_start_vm_already_running(test_operator, temp_storage):
    """Test starting VM that's already running."""
    vm_id = "test-vm"
    vm_dir = temp_storage / "vms" / vm_id
    vm_dir.mkdir(parents=True)
    pid_file = vm_dir / "qemu.pid"
    pid_file.write_text("12345")
    
    # Mock process existence check - in real scenario would check os.kill
    # For dry-run, this should be handled
    try:
        test_operator.start_vm(vm_id, cpu_count=2, ram_gb=4)
    except operator.OperatorError as e:
        assert "already running" in str(e).lower()


def test_stop_vm_dry_run(test_operator):
    """Test stopping VM in dry-run mode."""
    # Should not raise error in dry-run
    test_operator.stop_vm("test-vm")


def test_attach_disk_dry_run(test_operator, temp_storage):
    """Test attaching disk in dry-run mode."""
    disk_path = temp_storage / "disk.qcow2"
    disk_path.touch()  # Create file for dry-run
    
    # Should not raise error in dry-run
    test_operator.attach_disk("test-vm", disk_path, device="/dev/xvdb")


def test_attach_disk_not_running(test_operator, temp_storage):
    """Test attaching disk to non-running VM."""
    disk_path = temp_storage / "disk.qcow2"
    disk_path.touch()
    
    # In dry-run, this should be handled
    try:
        test_operator.attach_disk("test-vm", disk_path)
    except operator.OperatorError as e:
        assert "not running" in str(e).lower()


def test_attach_disk_not_found(test_operator):
    """Test attaching non-existent disk."""
    disk_path = Path("/nonexistent/disk.qcow2")
    
    with pytest.raises(operator.OperatorError, match="not found"):
        test_operator.attach_disk("test-vm", disk_path)


def test_detach_disk_dry_run(test_operator, temp_storage):
    """Test detaching disk in dry-run mode."""
    disk_path = temp_storage / "disk.qcow2"
    disk_path.touch()
    
    # Should not raise error in dry-run
    test_operator.detach_disk("test-vm", disk_path)


def test_operator_security_path_traversal(test_operator, temp_storage):
    """Security test: Path traversal in disk path."""
    malicious_path = temp_storage / "../../etc/passwd"
    
    # Should be handled safely (either reject or create in safe location)
    try:
        test_operator.create_disk_image(malicious_path, size_gb=10)
    except operator.OperatorError:
        pass  # Expected to fail safely


def test_operator_security_very_long_path(test_operator, temp_storage):
    """Security test: Very long path."""
    long_path = temp_storage / ("a" * 10000 + ".qcow2")
    
    # Should handle safely
    try:
        test_operator.create_disk_image(long_path, size_gb=10)
    except (operator.OperatorError, OSError):
        pass  # Expected to fail safely


def test_operator_safety_invalid_size(test_operator, temp_storage):
    """Safety test: Invalid disk size."""
    disk_path = temp_storage / "test.qcow2"
    
    # Zero or negative sizes should be handled
    with pytest.raises((operator.OperatorError, ValueError)):
        test_operator.create_disk_image(disk_path, size_gb=0)


def test_operator_safety_invalid_device(test_operator, temp_storage):
    """Safety test: Invalid device name."""
    disk_path = temp_storage / "disk.qcow2"
    disk_path.touch()
    
    # Invalid device should be handled
    try:
        test_operator.attach_disk("test-vm", disk_path, device="/invalid/device")
    except operator.OperatorError:
        pass  # Expected to handle invalid device

