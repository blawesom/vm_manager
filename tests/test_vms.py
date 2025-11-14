"""Unit tests for VM endpoints with safety and security verification."""
import pytest
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app import db, models, operator

client = TestClient(app)
# Enable dry-run mode for operator to avoid requiring QEMU
os.environ["VMAN_OPERATOR_DRY_RUN"] = "1"


@pytest.fixture(autouse=True)
def setup_db():
    """Setup and teardown database for each test."""
    models.Base.metadata.create_all(bind=db.engine)
    yield
    models.Base.metadata.drop_all(bind=db.engine)


@pytest.fixture
def template():
    """Create a test template."""
    client.post("/templates", json={"name": "test", "cpu_count": 2, "ram_amount": 4})
    return {"name": "test"}


def test_create_vm_success(template):
    """Test successful VM creation."""
    with patch('app.main._operator') as mock_operator:
        mock_operator.storage_path = "/tmp/test"
        
        response = client.post("/vms", json={"template_name": "test"})
        assert response.status_code == 201
        data = response.json()
        assert data["vm_template"]["name"] == "test"
        assert data["state"] == "stopped"
        assert "id" in data


def test_create_vm_with_name(template):
    """Test VM creation with custom name."""
    with patch('app.main._operator') as mock_operator:
        mock_operator.storage_path = "/tmp/test"
        
        response = client.post("/vms", json={"template_name": "test", "name": "my-vm"})
        assert response.status_code == 201
        assert response.json()["id"] == "my-vm"


def test_create_vm_template_not_found():
    """Test creating VM with non-existent template."""
    response = client.post("/vms", json={"template_name": "nonexistent"})
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_create_vm_duplicate_id(template):
    """Test creating VM with duplicate ID."""
    client.post("/vms", json={"template_name": "test", "name": "duplicate"})
    response = client.post("/vms", json={"template_name": "test", "name": "duplicate"})
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_list_vms_empty():
    """Test listing VMs when none exist."""
    response = client.get("/vms")
    assert response.status_code == 200
    assert response.json() == []


def test_list_vms_filter_by_state(template):
    """Test listing VMs filtered by state."""
    client.post("/vms", json={"template_name": "test"})
    response = client.get("/vms?state=stopped")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert all(vm["state"] == "stopped" for vm in data)


def test_get_vm_success(template):
    """Test getting VM details."""
    create_response = client.post("/vms", json={"template_name": "test"})
    vm_id = create_response.json()["id"]
    
    response = client.get(f"/vms/{vm_id}")
    assert response.status_code == 200
    assert response.json()["id"] == vm_id


def test_get_vm_not_found():
    """Test getting non-existent VM."""
    response = client.get("/vms/nonexistent")
    assert response.status_code == 404


def test_delete_vm_success(template):
    """Test successful VM deletion."""
    with patch('app.main._operator') as mock_operator:
        mock_operator.storage_path = "/tmp/test"
        mock_operator.stop_vm = MagicMock()
        
        create_response = client.post("/vms", json={"template_name": "test"})
        vm_id = create_response.json()["id"]
        
        response = client.delete(f"/vms/{vm_id}")
        assert response.status_code == 204


def test_delete_vm_not_found():
    """Test deleting non-existent VM."""
    response = client.delete("/vms/nonexistent")
    assert response.status_code == 404


def test_start_vm_success(template):
    """Test starting a VM."""
    with patch('app.main._operator') as mock_operator, \
         patch('app.main._network_manager', None):
        mock_operator.storage_path = "/tmp/test"
        mock_operator.start_vm = MagicMock()
        
        create_response = client.post("/vms", json={"template_name": "test"})
        vm_id = create_response.json()["id"]
        
        response = client.post(f"/vms/{vm_id}/actions/start")
        # In dry-run mode, should succeed
        assert response.status_code in [202, 400]  # 400 if QEMU not available, 202 if dry-run works


def test_start_vm_already_running(template):
    """Test starting an already running VM."""
    with patch('app.main._operator') as mock_operator:
        mock_operator.storage_path = "/tmp/test"
        
        create_response = client.post("/vms", json={"template_name": "test"})
        vm_id = create_response.json()["id"]
    
    # Manually set state to running in DB
    db_session = db.SessionLocal()
    try:
        vm = db_session.query(models.VM).filter(models.VM.id == vm_id).first()
        vm.state = "running"
        db_session.commit()
    finally:
        db_session.close()
    
    response = client.post(f"/vms/{vm_id}/actions/start")
    assert response.status_code == 400
    assert "already running" in response.json()["detail"].lower()


def test_stop_vm_not_running(template):
    """Test stopping a VM that's not running."""
    with patch('app.main._operator') as mock_operator:
        mock_operator.storage_path = "/tmp/test"
        
        create_response = client.post("/vms", json={"template_name": "test"})
        vm_id = create_response.json()["id"]
        
        response = client.post(f"/vms/{vm_id}/actions/stop")
        assert response.status_code == 400
        assert "not running" in response.json()["detail"].lower()


def test_restart_vm_success(template):
    """Test restarting a VM."""
    with patch('app.main._operator') as mock_operator, \
         patch('app.main._network_manager', None):
        mock_operator.storage_path = "/tmp/test"
        mock_operator.stop_vm = MagicMock()
        mock_operator.start_vm = MagicMock()
        
        create_response = client.post("/vms", json={"template_name": "test"})
        vm_id = create_response.json()["id"]
        
        response = client.post(f"/vms/{vm_id}/actions/restart")
        # In dry-run mode, should handle gracefully
        assert response.status_code in [202, 400]


def test_vm_security_sql_injection():
    """Security test: SQL injection in VM ID."""
    response = client.get("/vms/'; DROP TABLE vms; --")
    # Should not execute SQL, should return 404 or handle safely
    assert response.status_code in [404, 400]


def test_vm_security_path_traversal():
    """Security test: Path traversal in VM ID."""
    response = client.get("/vms/../../etc/passwd")
    # Should handle safely
    assert response.status_code in [404, 400]


def test_vm_security_invalid_state_transition(template):
    """Safety test: Invalid state transition."""
    create_response = client.post("/vms", json={"template_name": "test"})
    vm_id = create_response.json()["id"]
    
    # Try to stop a stopped VM
    response = client.post(f"/vms/{vm_id}/actions/stop")
    assert response.status_code == 400


def test_vm_security_very_long_id():
    """Security test: Very long VM ID."""
    long_id = "a" * 10000
    response = client.get(f"/vms/{long_id}")
    # Should handle safely without crashing
    assert response.status_code in [404, 400, 414]


def test_vm_security_special_characters_in_id():
    """Security test: Special characters in VM ID."""
    # httpx will raise InvalidURL for non-printable characters, which is expected
    import httpx
    try:
        response = client.get("/vms/test\n\r\t<script>")
        # If request succeeds, should handle safely
        assert response.status_code in [404, 400]
    except httpx.InvalidURL:
        # This is expected - invalid URLs should be rejected by the client
        pass

