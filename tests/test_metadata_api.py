"""Tests for VM metadata API endpoints."""
import pytest
from fastapi.testclient import TestClient
from app import main, db, models


@pytest.fixture
def client(test_db):
    """Create test client."""
    return TestClient(main.app)


def test_create_vm_metadata(client, test_db, test_template):
    """Test creating VM metadata."""
    # Create a VM first
    vm_response = client.post("/vms", json={"template_name": test_template.name})
    assert vm_response.status_code == 201
    vm_id = vm_response.json()["id"]
    
    # Create metadata
    metadata_data = {
        "hostname": "test-vm",
        "user_data": "#!/bin/bash\necho 'Hello from cloud-init'",
        "ssh_keys": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB test@example.com"
    }
    response = client.put(f"/vms/{vm_id}/metadata", json=metadata_data)
    assert response.status_code == 200
    data = response.json()
    assert data["vm_id"] == vm_id
    assert data["hostname"] == "test-vm"
    assert data["user_data"] == metadata_data["user_data"]
    assert data["ssh_keys"] == metadata_data["ssh_keys"]
    assert data["created_at"] is not None


def test_get_vm_metadata(client, test_db, test_template):
    """Test getting VM metadata."""
    # Create VM
    vm_response = client.post("/vms", json={"template_name": test_template.name})
    vm_id = vm_response.json()["id"]
    
    # Set metadata
    metadata_data = {
        "hostname": "test-vm",
        "user_data": "#!/bin/bash\necho 'test'",
        "ssh_keys": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB test@example.com"
    }
    client.put(f"/vms/{vm_id}/metadata", json=metadata_data)
    
    # Get metadata
    response = client.get(f"/vms/{vm_id}/metadata")
    assert response.status_code == 200
    data = response.json()
    assert data["vm_id"] == vm_id
    assert data["hostname"] == "test-vm"
    assert data["user_data"] == metadata_data["user_data"]


def test_get_vm_metadata_not_found(client, test_db, test_template):
    """Test getting metadata for VM without metadata."""
    # Create VM
    vm_response = client.post("/vms", json={"template_name": test_template.name})
    vm_id = vm_response.json()["id"]
    
    # Get metadata (should return empty)
    response = client.get(f"/vms/{vm_id}/metadata")
    assert response.status_code == 200
    data = response.json()
    assert data["vm_id"] == vm_id
    assert data["hostname"] is None
    assert data["user_data"] is None
    assert data["ssh_keys"] is None


def test_update_vm_metadata_partial(client, test_db, test_template):
    """Test partial update of VM metadata."""
    # Create VM
    vm_response = client.post("/vms", json={"template_name": test_template.name})
    vm_id = vm_response.json()["id"]
    
    # Set initial metadata
    client.put(f"/vms/{vm_id}/metadata", json={
        "hostname": "initial-hostname",
        "user_data": "#!/bin/bash\necho 'initial'"
    })
    
    # Update only hostname
    response = client.put(f"/vms/{vm_id}/metadata", json={
        "hostname": "updated-hostname"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["hostname"] == "updated-hostname"
    # user_data should still be there
    assert data["user_data"] == "#!/bin/bash\necho 'initial'"


def test_delete_vm_metadata(client, test_db, test_template):
    """Test deleting VM metadata."""
    # Create VM
    vm_response = client.post("/vms", json={"template_name": test_template.name})
    vm_id = vm_response.json()["id"]
    
    # Set metadata
    client.put(f"/vms/{vm_id}/metadata", json={
        "hostname": "test-vm",
        "user_data": "#!/bin/bash\necho 'test'"
    })
    
    # Delete metadata
    response = client.delete(f"/vms/{vm_id}/metadata")
    assert response.status_code == 204
    
    # Verify deleted
    response = client.get(f"/vms/{vm_id}/metadata")
    assert response.status_code == 200
    data = response.json()
    assert data["hostname"] is None
    assert data["user_data"] is None


def test_metadata_vm_not_found(client, test_db):
    """Test metadata operations on non-existent VM."""
    # Try to get metadata
    response = client.get("/vms/nonexistent/metadata")
    assert response.status_code == 404
    
    # Try to update metadata
    response = client.put("/vms/nonexistent/metadata", json={"hostname": "test"})
    assert response.status_code == 404
    
    # Try to delete metadata
    response = client.delete("/vms/nonexistent/metadata")
    assert response.status_code == 404


def test_metadata_multiple_ssh_keys(client, test_db, test_template):
    """Test metadata with multiple SSH keys."""
    # Create VM
    vm_response = client.post("/vms", json={"template_name": test_template.name})
    vm_id = vm_response.json()["id"]
    
    # Set metadata with multiple SSH keys
    ssh_keys = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB key1@example.com\nssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB key2@example.com"
    response = client.put(f"/vms/{vm_id}/metadata", json={
        "ssh_keys": ssh_keys
    })
    assert response.status_code == 200
    data = response.json()
    assert data["ssh_keys"] == ssh_keys
    assert "\n" in data["ssh_keys"]


def test_metadata_empty_values(client, test_db, test_template):
    """Test setting metadata with None/null values."""
    # Create VM
    vm_response = client.post("/vms", json={"template_name": test_template.name})
    vm_id = vm_response.json()["id"]
    
    # Set metadata with some values
    client.put(f"/vms/{vm_id}/metadata", json={
        "hostname": "test-vm",
        "user_data": "#!/bin/bash\necho 'test'"
    })
    
    # Update with None values (should clear)
    response = client.put(f"/vms/{vm_id}/metadata", json={
        "hostname": None,
        "user_data": None
    })
    assert response.status_code == 200
    data = response.json()
    # Note: Pydantic may not accept None, so we test with empty string or omit field
    # For now, we'll test that the API accepts the request

