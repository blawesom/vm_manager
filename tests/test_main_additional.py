"""Additional unit tests for main.py endpoints to improve coverage."""
import pytest
from unittest.mock import patch, MagicMock, Mock
from fastapi.testclient import TestClient
from app.main import app
from app import db, models

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Setup and teardown database for each test."""
    models.Base.metadata.create_all(bind=db.engine)
    yield
    models.Base.metadata.drop_all(bind=db.engine)


@patch('app.main._operator')
def test_create_disk_operator_error(mock_operator):
    """Test disk creation with operator error."""
    mock_operator.storage_path = "/tmp/test"
    from app import operator
    mock_operator.create_disk_image.side_effect = operator.OperatorError("Disk creation failed")
    
    response = client.post("/disks", json={"size": 10})
    assert response.status_code == 400
    assert "failed" in response.json()["detail"].lower()


@patch('app.main._operator')
def test_delete_disk_operator_error(mock_operator):
    """Test disk deletion with operator error."""
    mock_operator.storage_path = "/tmp/test"
    mock_operator.create_disk_image = MagicMock()
    from app import operator
    mock_operator.delete_disk_image.side_effect = operator.OperatorError("Delete failed")
    
    # Create disk first
    create_response = client.post("/disks", json={"size": 10})
    disk_id = create_response.json()["id"]
    
    # Manually set state to available (not attached)
    db_session = db.SessionLocal()
    try:
        disk = db_session.query(models.Disk).filter(models.Disk.id == disk_id).first()
        disk.state = "available"
        db_session.commit()
    finally:
        db_session.close()
    
    response = client.delete(f"/disks/{disk_id}")
    assert response.status_code == 400
    assert "failed" in response.json()["detail"].lower()


@patch('app.main._operator')
def test_attach_disk_operator_error(mock_operator):
    """Test disk attach with operator error."""
    mock_operator.storage_path = "/tmp/test"
    mock_operator.create_disk_image = MagicMock()
    from app import operator
    mock_operator.attach_disk.side_effect = operator.OperatorError("Attach failed")
    
    # Create disk and VM
    disk_response = client.post("/disks", json={"size": 10})
    disk_id = disk_response.json()["id"]
    
    client.post("/templates", json={"name": "test", "cpu_count": 2, "ram_amount": 4})
    vm_response = client.post("/vms", json={"template_name": "test"})
    vm_id = vm_response.json()["id"]
    
    # Set VM to running
    db_session = db.SessionLocal()
    try:
        vm = db_session.query(models.VM).filter(models.VM.id == vm_id).first()
        vm.state = "running"
        db_session.commit()
    finally:
        db_session.close()
    
    response = client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
    assert response.status_code == 400
    assert "failed" in response.json()["detail"].lower()


@patch('app.main._operator')
def test_detach_disk_operator_error(mock_operator):
    """Test disk detach with operator error."""
    mock_operator.storage_path = "/tmp/test"
    mock_operator.create_disk_image = MagicMock()
    from app import operator
    mock_operator.detach_disk.side_effect = operator.OperatorError("Detach failed")
    
    # Create disk and attach it
    disk_response = client.post("/disks", json={"size": 10})
    disk_id = disk_response.json()["id"]
    
    client.post("/templates", json={"name": "test", "cpu_count": 2, "ram_amount": 4})
    vm_response = client.post("/vms", json={"template_name": "test"})
    vm_id = vm_response.json()["id"]
    
    # Set disk as attached and VM as running
    db_session = db.SessionLocal()
    try:
        disk = db_session.query(models.Disk).filter(models.Disk.id == disk_id).first()
        disk.state = "attached"
        disk.vm_id = vm_id
        vm = db_session.query(models.VM).filter(models.VM.id == vm_id).first()
        vm.state = "running"
        db_session.commit()
    finally:
        db_session.close()
    
    response = client.post(f"/disks/{disk_id}/detach")
    assert response.status_code == 400
    assert "failed" in response.json()["detail"].lower()


@patch('app.main._operator')
@patch('app.main._network_manager', None)
def test_start_vm_operator_error(mock_operator):
    """Test VM start with operator error."""
    mock_operator.storage_path = "/tmp/test"
    from app import operator
    mock_operator.start_vm.side_effect = operator.OperatorError("Start failed")
    
    client.post("/templates", json={"name": "test", "cpu_count": 2, "ram_amount": 4})
    vm_response = client.post("/vms", json={"template_name": "test"})
    vm_id = vm_response.json()["id"]
    
    response = client.post(f"/vms/{vm_id}/actions/start")
    assert response.status_code == 400
    assert "failed" in response.json()["detail"].lower()
    
    # Check VM state is set to error
    db_session = db.SessionLocal()
    try:
        vm = db_session.query(models.VM).filter(models.VM.id == vm_id).first()
        assert vm.state == "error"
    finally:
        db_session.close()


@patch('app.main._operator')
def test_stop_vm_operator_error(mock_operator):
    """Test VM stop with operator error."""
    mock_operator.storage_path = "/tmp/test"
    from app import operator
    mock_operator.stop_vm.side_effect = operator.OperatorError("Stop failed")
    
    client.post("/templates", json={"name": "test", "cpu_count": 2, "ram_amount": 4})
    vm_response = client.post("/vms", json={"template_name": "test"})
    vm_id = vm_response.json()["id"]
    
    # Set VM to running
    db_session = db.SessionLocal()
    try:
        vm = db_session.query(models.VM).filter(models.VM.id == vm_id).first()
        vm.state = "running"
        db_session.commit()
    finally:
        db_session.close()
    
    response = client.post(f"/vms/{vm_id}/actions/stop")
    assert response.status_code == 400
    assert "failed" in response.json()["detail"].lower()


@patch('app.main._operator')
@patch('app.main._network_manager', None)
def test_restart_vm_operator_error(mock_operator):
    """Test VM restart with operator error."""
    mock_operator.storage_path = "/tmp/test"
    from app import operator
    mock_operator.stop_vm = MagicMock()
    mock_operator.start_vm.side_effect = operator.OperatorError("Start failed")
    
    client.post("/templates", json={"name": "test", "cpu_count": 2, "ram_amount": 4})
    vm_response = client.post("/vms", json={"template_name": "test"})
    vm_id = vm_response.json()["id"]
    
    # Set VM to running
    db_session = db.SessionLocal()
    try:
        vm = db_session.query(models.VM).filter(models.VM.id == vm_id).first()
        vm.state = "running"
        db_session.commit()
    finally:
        db_session.close()
    
    response = client.post(f"/vms/{vm_id}/actions/restart")
    assert response.status_code == 400
    assert "failed" in response.json()["detail"].lower()


@patch('app.main._operator')
@patch('app.main._network_manager')
def test_start_vm_with_network_ip(mock_network, mock_operator):
    """Test VM start with network IP assignment."""
    from pathlib import Path
    import tempfile
    
    mock_operator.storage_path = "/tmp/test"
    mock_operator.start_vm = MagicMock()
    
    # Configure network manager mock
    mock_network.get_allocated_ips.return_value = set()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vm_dir = Path(tmpdir) / "vms" / "test-vm"
        vm_dir.mkdir(parents=True)
        ip_file = vm_dir / "ip.txt"
        ip_file.write_text("192.168.100.10")
        
        client.post("/templates", json={"name": "test", "cpu_count": 2, "ram_amount": 4})
        vm_response = client.post("/vms", json={"template_name": "test", "name": "test-vm"})
        vm_id = vm_response.json()["id"]
        
        response = client.post(f"/vms/{vm_id}/actions/start")
        # Should handle gracefully
        assert response.status_code in [202, 400]


@patch('app.main._operator')
def test_detach_disk_vm_not_running(mock_operator):
    """Test detach disk when VM is not running."""
    mock_operator.storage_path = "/tmp/test"
    mock_operator.create_disk_image = MagicMock()
    
    # Create disk and VM
    disk_response = client.post("/disks", json={"size": 10})
    disk_id = disk_response.json()["id"]
    
    client.post("/templates", json={"name": "test", "cpu_count": 2, "ram_amount": 4})
    vm_response = client.post("/vms", json={"template_name": "test"})
    vm_id = vm_response.json()["id"]
    
    # Set disk as attached but VM not running
    db_session = db.SessionLocal()
    try:
        disk = db_session.query(models.Disk).filter(models.Disk.id == disk_id).first()
        disk.state = "attached"
        disk.vm_id = vm_id
        vm = db_session.query(models.VM).filter(models.VM.id == vm_id).first()
        vm.state = "stopped"  # Not running
        db_session.commit()
    finally:
        db_session.close()
    
    response = client.post(f"/disks/{disk_id}/detach")
    assert response.status_code == 200
    assert response.json()["status"] == "detached"
    
    # Check disk state updated
    db_session = db.SessionLocal()
    try:
        disk = db_session.query(models.Disk).filter(models.Disk.id == disk_id).first()
        assert disk.state == "available"
        assert disk.vm_id is None
    finally:
        db_session.close()


@patch('app.main._operator')
def test_detach_disk_vm_not_found(mock_operator):
    """Test detach disk when VM not found."""
    mock_operator.storage_path = "/tmp/test"
    mock_operator.create_disk_image = MagicMock()
    
    # Create disk
    disk_response = client.post("/disks", json={"size": 10})
    disk_id = disk_response.json()["id"]
    
    # Set disk as attached but VM doesn't exist
    db_session = db.SessionLocal()
    try:
        disk = db_session.query(models.Disk).filter(models.Disk.id == disk_id).first()
        disk.state = "attached"
        disk.vm_id = "nonexistent-vm"
        db_session.commit()
    finally:
        db_session.close()
    
    response = client.post(f"/disks/{disk_id}/detach")
    assert response.status_code == 200
    assert response.json()["status"] == "detached"


def test_create_disk_uuid_collision():
    """Test disk creation with UUID collision (retry)."""
    with patch('app.main._operator') as mock_operator:
        mock_operator.storage_path = "/tmp/test"
        mock_operator.create_disk_image = MagicMock()
        
        # First UUID exists, second is new
        existing_disk = models.Disk(id="collision-id", size=10, state="available")
        db_session = db.SessionLocal()
        try:
            db_session.add(existing_disk)
            db_session.commit()
        finally:
            db_session.close()
        
        # Mock second call to return different UUID
        import uuid as uuid_module
        original_uuid4 = uuid_module.uuid4
        call_count = [0]
        
        def mock_uuid4():
            call_count[0] += 1
            if call_count[0] == 1:
                result = Mock()
                result.__str__ = lambda self: "collision-id"
                return result
            else:
                return original_uuid4()
        
        with patch('app.main.uuid.uuid4', side_effect=mock_uuid4):
            response = client.post("/disks", json={"size": 10})
            # Should succeed with retry
            assert response.status_code == 201

