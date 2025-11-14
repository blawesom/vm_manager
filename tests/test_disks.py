"""Unit tests for disk endpoints with safety and security verification."""
import pytest
import os
from fastapi.testclient import TestClient
from app.main import app
from app import db, models

client = TestClient(app)
# Enable dry-run mode for operator
os.environ["VMAN_OPERATOR_DRY_RUN"] = "1"


@pytest.fixture(autouse=True)
def setup_db():
    """Setup and teardown database for each test."""
    models.Base.metadata.create_all(bind=db.engine)
    yield
    models.Base.metadata.drop_all(bind=db.engine)


def test_create_disk_success():
    """Test successful disk creation."""
    response = client.post("/disks", json={"size": 10})
    assert response.status_code == 201
    data = response.json()
    assert data["size"] == 10
    assert data["state"] == "available"
    assert "id" in data


def test_create_disk_with_mount_point():
    """Test disk creation with mount point."""
    response = client.post("/disks", json={"size": 20, "mount_point": "/dev/xvdb"})
    assert response.status_code == 201
    assert response.json()["mount_point"] == "/dev/xvdb"


def test_create_disk_invalid_size():
    """Test disk creation with invalid size."""
    response = client.post("/disks", json={"size": 0})
    assert response.status_code == 422  # Validation error


def test_create_disk_negative_size():
    """Test disk creation with negative size."""
    response = client.post("/disks", json={"size": -1})
    assert response.status_code == 422  # Validation error


def test_list_disks_empty():
    """Test listing disks when none exist."""
    response = client.get("/disks")
    assert response.status_code == 200
    assert response.json() == []


def test_list_disks_multiple():
    """Test listing multiple disks."""
    client.post("/disks", json={"size": 10})
    client.post("/disks", json={"size": 20})
    
    response = client.get("/disks")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_get_disk_success():
    """Test getting disk details."""
    create_response = client.post("/disks", json={"size": 10})
    disk_id = create_response.json()["id"]
    
    response = client.get(f"/disks/{disk_id}")
    assert response.status_code == 200
    assert response.json()["id"] == disk_id


def test_get_disk_not_found():
    """Test getting non-existent disk."""
    response = client.get("/disks/nonexistent")
    assert response.status_code == 404


def test_delete_disk_success():
    """Test successful disk deletion."""
    create_response = client.post("/disks", json={"size": 10})
    disk_id = create_response.json()["id"]
    
    response = client.delete(f"/disks/{disk_id}")
    assert response.status_code == 204


def test_delete_disk_not_found():
    """Test deleting non-existent disk."""
    response = client.delete("/disks/nonexistent")
    assert response.status_code == 404


def test_delete_attached_disk():
    """Test deleting attached disk fails."""
    # Create disk and mark as attached
    create_response = client.post("/disks", json={"size": 10})
    disk_id = create_response.json()["id"]
    
    # Manually set state to attached
    db_session = db.SessionLocal()
    try:
        disk = db_session.query(models.Disk).filter(models.Disk.id == disk_id).first()
        disk.state = "attached"
        db_session.commit()
    finally:
        db_session.close()
    
    response = client.delete(f"/disks/{disk_id}")
    assert response.status_code == 400
    assert "attached" in response.json()["detail"].lower()


def test_attach_disk_missing_vm_id():
    """Test attaching disk without VM ID."""
    create_response = client.post("/disks", json={"size": 10})
    disk_id = create_response.json()["id"]
    
    response = client.post(f"/disks/{disk_id}/attach", json={})
    assert response.status_code == 400
    assert "vm_id" in response.json()["detail"].lower()


def test_attach_disk_vm_not_found():
    """Test attaching disk to non-existent VM."""
    create_response = client.post("/disks", json={"size": 10})
    disk_id = create_response.json()["id"]
    
    response = client.post(f"/disks/{disk_id}/attach", json={"vm_id": "nonexistent"})
    assert response.status_code == 404


def test_attach_disk_already_attached():
    """Test attaching already attached disk."""
    create_response = client.post("/disks", json={"size": 10})
    disk_id = create_response.json()["id"]
    
    # Mark as attached
    db_session = db.SessionLocal()
    try:
        disk = db_session.query(models.Disk).filter(models.Disk.id == disk_id).first()
        disk.state = "attached"
        disk.vm_id = "some-vm"
        db_session.commit()
    finally:
        db_session.close()
    
    response = client.post(f"/disks/{disk_id}/attach", json={"vm_id": "some-vm"})
    assert response.status_code == 400
    assert "already attached" in response.json()["detail"].lower()


def test_detach_disk_not_attached():
    """Test detaching disk that's not attached."""
    create_response = client.post("/disks", json={"size": 10})
    disk_id = create_response.json()["id"]
    
    response = client.post(f"/disks/{disk_id}/detach")
    assert response.status_code == 400
    assert "not attached" in response.json()["detail"].lower()


def test_disk_security_sql_injection():
    """Security test: SQL injection in disk ID."""
    response = client.get("/disks/'; DROP TABLE disks; --")
    # Should not execute SQL
    assert response.status_code in [404, 400]


def test_disk_security_path_traversal():
    """Security test: Path traversal in disk ID."""
    response = client.get("/disks/../../etc/passwd")
    # Should handle safely
    assert response.status_code in [404, 400]


def test_disk_security_very_large_size():
    """Security test: Very large disk size."""
    response = client.post("/disks", json={"size": 999999999999})
    # Should handle safely (create or reject, but not crash)
    assert response.status_code in [201, 400, 422]


def test_disk_security_invalid_mount_point():
    """Security test: Invalid mount point format."""
    response = client.post("/disks", json={"size": 10, "mount_point": "../../etc/passwd"})
    # Should handle safely
    assert response.status_code in [201, 400, 422]

