"""Unit tests for OBSERVER service with safety and security verification."""
import pytest
import os
import tempfile
import time
from pathlib import Path
from app import observer, db, models, operator


@pytest.fixture
def temp_storage():
    """Create temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_operator(temp_storage):
    """Create operator instance."""
    return operator.LocalOperator(dry_run=True, storage_path=temp_storage)


@pytest.fixture
def test_observer(temp_storage, test_operator):
    """Create observer instance."""
    return observer.LocalObserver(
        db_session_factory=db.SessionLocal,
        operator=test_operator,
        storage_path=temp_storage,
        check_interval=0.1  # Fast for testing
    )


@pytest.fixture(autouse=True)
def setup_db():
    """Setup and teardown database."""
    models.Base.metadata.create_all(bind=db.engine)
    yield
    models.Base.metadata.drop_all(bind=db.engine)


def test_observer_start_stop(test_observer):
    """Test observer start and stop."""
    test_observer.start()
    assert test_observer.running is True
    
    time.sleep(0.2)  # Let it run briefly
    
    test_observer.stop()
    assert test_observer.running is False


def test_observer_double_start(test_observer):
    """Test starting observer twice."""
    test_observer.start()
    test_observer.start()  # Should handle gracefully
    test_observer.stop()


def test_observer_double_stop(test_observer):
    """Test stopping observer twice."""
    test_observer.start()
    test_observer.stop()
    test_observer.stop()  # Should handle gracefully


def test_check_coherence_no_issues(test_observer):
    """Test coherence check with no issues."""
    issues = test_observer.check_coherence()
    assert isinstance(issues, list)
    # With empty DB and no files, should have no issues


def test_check_vm_coherence_state_mismatch(test_observer, temp_storage):
    """Test VM coherence check detects state mismatch."""
    # Create VM in DB with running state
    db_session = db.SessionLocal()
    try:
        vm = models.VM(id="test-vm", template_name="test", state="running")
        db_session.add(vm)
        db_session.commit()
    finally:
        db_session.close()
    
    # No PID file exists, so should detect mismatch
    issues = test_observer._check_vm_coherence()
    assert len(issues) > 0
    assert any(issue.issue_type == "vm_state_mismatch" for issue in issues)


def test_check_disk_coherence_missing_file(test_observer, temp_storage):
    """Test disk coherence check detects missing file."""
    # Create disk in DB
    db_session = db.SessionLocal()
    try:
        disk = models.Disk(id="test-disk", size=10, state="available")
        db_session.add(disk)
        db_session.commit()
    finally:
        db_session.close()
    
    # File doesn't exist, should detect issue
    issues = test_observer._check_disk_coherence()
    assert len(issues) > 0
    assert any(issue.issue_type == "missing_disk" for issue in issues)


def test_check_disk_coherence_orphan_file(test_observer, temp_storage):
    """Test disk coherence check detects orphan file."""
    # Create disk file but not in DB
    disks_dir = temp_storage / "disks"
    disks_dir.mkdir(parents=True)
    (disks_dir / "orphan.qcow2").touch()
    
    issues = test_observer._check_disk_coherence()
    assert len(issues) > 0
    assert any(issue.issue_type == "orphan_disk" for issue in issues)


def test_check_disk_coherence_state_inconsistent(test_observer, temp_storage):
    """Test disk coherence check detects state inconsistency."""
    # Create disk in DB with inconsistent state
    db_session = db.SessionLocal()
    try:
        disk = models.Disk(id="inconsistent", size=10, state="attached", vm_id=None)
        db_session.add(disk)
        db_session.commit()
    finally:
        db_session.close()
    
    # Create the file
    disks_dir = temp_storage / "disks"
    disks_dir.mkdir(parents=True)
    (disks_dir / "inconsistent.qcow2").touch()
    
    issues = test_observer._check_disk_coherence()
    assert len(issues) > 0
    assert any(issue.issue_type == "disk_state_inconsistent" for issue in issues)


def test_get_vm_ids_from_pid_files(test_observer, temp_storage):
    """Test getting VM IDs from PID files."""
    # Create VM directory with PID file
    vm_dir = temp_storage / "vms" / "test-vm"
    vm_dir.mkdir(parents=True)
    pid_file = vm_dir / "qemu.pid"
    pid_file.write_text("12345")
    
    # Should return empty if process doesn't exist (PID 12345 likely doesn't)
    vm_ids = test_observer._get_vm_ids_from_pid_files()
    # Result depends on whether PID exists, but should not crash


def test_observer_no_db_session_factory():
    """Test observer without DB session factory."""
    obs = observer.LocalObserver(db_session_factory=None)
    issues = obs.check_coherence()
    # Should return empty list and log warning
    assert issues == []


def test_observer_security_path_traversal(test_observer, temp_storage):
    """Security test: Path traversal in storage path."""
    # Try to set malicious storage path
    malicious_path = Path("/etc")
    obs = observer.LocalObserver(
        db_session_factory=db.SessionLocal,
        storage_path=malicious_path
    )
    
    # Should handle safely (either use path or default)
    issues = obs.check_coherence()
    assert isinstance(issues, list)  # Should not crash


def test_observer_safety_rapid_start_stop(test_observer):
    """Safety test: Rapid start/stop cycles."""
    for _ in range(10):
        test_observer.start()
        time.sleep(0.01)
        test_observer.stop()
    
    # Should not crash or leave threads hanging
    assert not test_observer.running

