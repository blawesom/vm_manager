"""Shared fixtures for VMAN integration tests."""
import pytest
import shutil
import os
import tempfile
from pathlib import Path
from typing import Generator, Optional, Dict
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db, models, operator, observer, network_manager, main


@pytest.fixture(scope="session")
def qemu_available() -> Optional[Dict[str, str]]:
    """Check if QEMU is available for integration tests.
    
    Returns dict with 'bin' and 'img' keys if available, None otherwise.
    Skips tests if QEMU not available.
    """
    qemu_bin = shutil.which("qemu-system-x86_64") or shutil.which("qemu-kvm")
    qemu_img = shutil.which("qemu-img")
    
    if not qemu_bin or not qemu_img:
        pytest.skip("QEMU not available for integration tests")
    
    return {"bin": qemu_bin, "img": qemu_img}


@pytest.fixture(scope="session")
def temp_storage(tmp_path_factory) -> Path:
    """Create temporary storage directory for integration tests.
    
    This directory will be used for VM and disk storage during tests.
    Automatically cleaned up after test session.
    """
    storage = tmp_path_factory.mktemp("vman_test_storage")
    return storage


@pytest.fixture(scope="function")
def test_db() -> Generator:
    """Create isolated test database for each test.
    
    Creates a temporary SQLite database, sets up tables, and cleans up after test.
    """
    # Create temporary database file
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    
    # Create engine and session for test database
    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # Create tables
    models.Base.metadata.create_all(bind=test_engine)
    
    # Temporarily replace the global db session
    original_engine = db.engine
    original_session = db.SessionLocal
    db.engine = test_engine
    db.SessionLocal = test_session
    
    yield test_session()
    
    # Restore original db session
    db.engine = original_engine
    db.SessionLocal = original_session
    
    # Cleanup
    models.Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    os.unlink(db_path)


@pytest.fixture(scope="function")
def test_network_manager(temp_storage: Path) -> network_manager.NetworkManager:
    """Create test network manager.
    
    Uses test VLAN and bridge configuration suitable for testing.
    """
    return network_manager.NetworkManager(
        vlan_id=999,  # Use high VLAN ID to avoid conflicts
        bridge_name="br-vman-test",
        subnet="192.168.199.0/24",
        gateway="192.168.199.1",
        dns=["8.8.8.8", "8.8.4.4"],
        dry_run=True  # Use dry-run for tests unless network tests enabled
    )


@pytest.fixture(scope="function")
def test_operator(temp_storage: Path, test_network_manager, qemu_available) -> operator.LocalOperator:
    """Create test operator instance.
    
    Uses temporary storage and test network manager.
    """
    # Determine if we should use dry-run
    # Check environment variable first, then fall back to checking QEMU availability
    dry_run_env = os.environ.get("VMAN_OPERATOR_DRY_RUN")
    if dry_run_env is not None:
        use_dry_run = dry_run_env == "1"
    else:
        # If not explicitly set, use dry-run if QEMU not available
        use_dry_run = not qemu_available
    
    return operator.LocalOperator(
        dry_run=use_dry_run,
        storage_path=temp_storage,
        network_manager=test_network_manager
    )


@pytest.fixture(scope="function")
def test_observer(test_db, test_operator) -> observer.LocalObserver:
    """Create test observer instance.
    
    Uses test database and operator.
    """
    def db_session_factory():
        return test_db
    
    return observer.LocalObserver(
        db_session_factory=db_session_factory,
        operator=test_operator,
        check_interval=1.0  # Faster checks for tests
    )


@pytest.fixture(scope="function")
def test_client(test_db, test_operator, test_observer, temp_storage) -> TestClient:
    """Create FastAPI test client with test services.
    
    This fixture sets up a test client with real operator and observer instances.
    """
    # Store original globals
    original_operator = main._operator
    original_observer = main._observer
    original_network_manager = main._network_manager
    
    # Set test instances
    main._operator = test_operator
    main._observer = test_observer
    main._network_manager = test_operator.network_manager
    
    # Create test client
    client = TestClient(main.app)
    
    # Start observer for tests
    test_observer.start()
    
    yield client
    
    # Stop observer
    test_observer.stop()
    
    # Restore original globals
    main._operator = original_operator
    main._observer = original_observer
    main._network_manager = original_network_manager


@pytest.fixture(scope="function")
def test_template(test_client: TestClient) -> Dict:
    """Create a test template for use in tests.
    
    Returns template data dict.
    """
    # Try to create template, handle case where it might already exist
    response = test_client.post("/templates", json={
        "name": "test-template",
        "cpu_count": 1,
        "ram_amount": 512  # Small for fast tests
    })
    
    if response.status_code == 400 and "already exists" in response.json().get("detail", "").lower():
        # Template already exists, fetch it
        response = test_client.get("/templates")
        templates = response.json()
        for template in templates:
            if template["name"] == "test-template":
                return template
        # If not found in list, try to get it directly (though endpoint doesn't exist)
        # Fall through to assertion error
    elif response.status_code == 201:
        return response.json()
    
    # If we get here, something went wrong
    assert response.status_code == 201, f"Failed to create test template: {response.status_code} - {response.text}"
    return response.json()


@pytest.fixture(scope="function")
def cleanup_test_vms(test_client: TestClient) -> Generator:
    """Fixture to cleanup VMs created during test.
    
    Yields nothing, but cleans up all VMs after test completes.
    """
    yield
    
    # Get all VMs
    response = test_client.get("/vms")
    if response.status_code == 200:
        vms = response.json()
        for vm in vms:
            vm_id = vm["id"]
            # Stop if running
            if vm["state"] == "running":
                test_client.post(f"/vms/{vm_id}/actions/stop")
            # Delete
            test_client.delete(f"/vms/{vm_id}")


@pytest.fixture(scope="function")
def cleanup_test_disks(test_client: TestClient) -> Generator:
    """Fixture to cleanup disks created during test.
    
    Yields nothing, but cleans up all disks after test completes.
    """
    yield
    
    # Get all disks
    response = test_client.get("/disks")
    if response.status_code == 200:
        disks = response.json()
        for disk in disks:
            disk_id = disk["id"]
            # Detach if attached
            if disk["state"] == "attached":
                test_client.post(f"/disks/{disk_id}/detach")
            # Delete
            test_client.delete(f"/disks/{disk_id}")


@pytest.fixture(scope="function")
def cleanup_test_templates(test_client: TestClient) -> Generator:
    """Fixture to cleanup templates created during test.
    
    Yields nothing, but cleans up all templates after test completes.
    """
    yield
    
    # Get all templates
    response = test_client.get("/templates")
    if response.status_code == 200:
        templates = response.json()
        for template in templates:
            template_name = template["name"]
            test_client.delete(f"/templates/{template_name}")

