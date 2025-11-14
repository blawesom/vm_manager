"""Additional unit tests for observer.py to improve coverage."""
import pytest
from unittest.mock import patch, MagicMock, Mock
from pathlib import Path
from app import observer, db, models


@pytest.fixture(autouse=True)
def setup_db():
    """Setup and teardown database for each test."""
    models.Base.metadata.create_all(bind=db.engine)
    yield
    models.Base.metadata.drop_all(bind=db.engine)


@pytest.fixture
def temp_storage(tmp_path):
    """Create temporary storage directory."""
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "vms").mkdir()
    (storage / "disks").mkdir()
    return storage


@pytest.fixture
def test_operator(temp_storage):
    """Create test operator."""
    from app import operator
    return operator.LocalOperator(dry_run=True, storage_path=temp_storage)


@pytest.fixture
def test_observer(temp_storage, test_operator):
    """Create test observer."""
    return observer.LocalObserver(
        db_session_factory=db.SessionLocal,
        operator=test_operator,
        check_interval=0.1  # Fast for testing
    )


def test_check_vm_coherence_orphan_process(temp_storage, test_observer):
    """Test VM coherence check detects orphan process."""
    # Create PID file but no VM in DB
    vm_dir = temp_storage / "vms" / "orphan-vm"
    vm_dir.mkdir(parents=True)
    pid_file = vm_dir / "qemu.pid"
    pid_file.write_text("12345")
    
    # Mock process exists - need to patch os.kill to not raise
    with patch('os.kill') as mock_kill:
        mock_kill.return_value = None  # Process exists (os.kill returns None on success)
        
        issues = test_observer._check_vm_coherence()
        assert len(issues) > 0
        # The issue type is "orphan_process" not "orphan_vm" based on observer code
        assert any(issue.issue_type == "orphan_process" for issue in issues)


def test_check_vm_coherence_running_matches(temp_storage, test_observer):
    """Test VM coherence check when running state matches."""
    # Create VM in DB with running state
    db_session = db.SessionLocal()
    try:
        vm = models.VM(id="test-vm", template_name="test", state="running")
        db_session.add(vm)
        db_session.commit()
    finally:
        db_session.close()
    
    # Create PID file
    vm_dir = temp_storage / "vms" / "test-vm"
    vm_dir.mkdir(parents=True)
    pid_file = vm_dir / "qemu.pid"
    pid_file.write_text("12345")
    
    # Mock process exists
    with patch('os.kill') as mock_kill:
        mock_kill.return_value = None  # Process exists
        
        issues = test_observer._check_vm_coherence()
        # Should have no issues
        assert len(issues) == 0


def test_check_disk_coherence_attached_missing_file(temp_storage, test_observer):
    """Test disk coherence check when attached disk file is missing."""
    # Create disk in DB with attached state
    db_session = db.SessionLocal()
    try:
        disk = models.Disk(id="test-disk", size=10, state="attached", vm_id="vm-1")
        db_session.add(disk)
        db_session.commit()
    finally:
        db_session.close()
    
    # File doesn't exist
    issues = test_observer._check_disk_coherence()
    assert len(issues) > 0
    assert any(issue.issue_type == "missing_disk" for issue in issues)


def test_check_disk_coherence_available_with_file(temp_storage, test_observer):
    """Test disk coherence check when available disk has file."""
    # Create disk in DB with available state
    db_session = db.SessionLocal()
    try:
        disk = models.Disk(id="test-disk", size=10, state="available")
        db_session.add(disk)
        db_session.commit()
    finally:
        db_session.close()
    
    # Create disk file
    disks_dir = temp_storage / "disks"
    (disks_dir / "test-disk.qcow2").touch()
    
    issues = test_observer._check_disk_coherence()
    # Should have no issues (available disk can have file)
    assert len(issues) == 0


def test_get_vm_ids_from_pid_files_multiple(temp_storage, test_observer):
    """Test getting multiple VM IDs from PID files."""
    # Create multiple PID files
    for vm_id in ["vm-1", "vm-2", "vm-3"]:
        vm_dir = temp_storage / "vms" / vm_id
        vm_dir.mkdir(parents=True)
        pid_file = vm_dir / "qemu.pid"
        pid_file.write_text("12345")
    
    # Mock os.kill to indicate processes exist
    with patch('os.kill') as mock_kill:
        mock_kill.return_value = None  # Process exists
        
        vm_ids = test_observer._get_vm_ids_from_pid_files()
        assert len(vm_ids) == 3
        assert "vm-1" in vm_ids
        assert "vm-2" in vm_ids
        assert "vm-3" in vm_ids


def test_get_vm_ids_from_pid_files_invalid_pid(temp_storage, test_observer):
    """Test getting VM IDs with invalid PID file."""
    # Create PID file with invalid content
    vm_dir = temp_storage / "vms" / "invalid-vm"
    vm_dir.mkdir(parents=True)
    pid_file = vm_dir / "qemu.pid"
    pid_file.write_text("not-a-number")
    
    vm_ids = test_observer._get_vm_ids_from_pid_files()
    # Should skip invalid PID files
    assert "invalid-vm" not in vm_ids


def test_check_coherence_with_issues(temp_storage, test_observer):
    """Test coherence check that finds issues."""
    # Create VM in DB but no process
    db_session = db.SessionLocal()
    try:
        vm = models.VM(id="test-vm", template_name="test", state="running")
        db_session.add(vm)
        db_session.commit()
    finally:
        db_session.close()
    
    # No PID file, so should detect mismatch
    issues = test_observer.check_coherence()
    assert len(issues) > 0


def test_observer_stop_when_not_running(test_observer):
    """Test stopping observer when not running."""
    # Observer not started
    test_observer.stop()
    # Should not raise
    assert test_observer.running is False


def test_check_vm_coherence_stopped_matches(temp_storage, test_observer):
    """Test VM coherence check when stopped state matches."""
    # Create VM in DB with stopped state
    db_session = db.SessionLocal()
    try:
        vm = models.VM(id="test-vm", template_name="test", state="stopped")
        db_session.add(vm)
        db_session.commit()
    finally:
        db_session.close()
    
    # No PID file
    issues = test_observer._check_vm_coherence()
    # Should have no issues
    assert len(issues) == 0

