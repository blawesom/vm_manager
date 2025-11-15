"""Example integration test to demonstrate the pattern.

This file shows how to write integration tests using the shared fixtures.
This is a template - actual integration tests should be in separate files.
"""
import os
import pytest
import time
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_vm_lifecycle_example(
    test_client: TestClient,
    test_template: dict,
    cleanup_test_vms,
    qemu_available
):
    """Example: Test complete VM lifecycle with real QEMU.
    
    This demonstrates the pattern for integration tests:
    1. Use test_client fixture for API calls
    2. Use test_template fixture for templates
    3. Use cleanup fixtures to ensure cleanup
    4. Mark with @pytest.mark.integration
    5. Skip if QEMU not available
    """
    # Create VM
    response = test_client.post("/vms", json={
        "template_name": test_template["name"],
        "name": "test-vm-integration"
    })
    assert response.status_code == 201
    vm_data = response.json()
    vm_id = vm_data["id"]
    assert vm_data["state"] == "stopped"
    
    # Start VM (only if QEMU available and not in dry-run)
    if qemu_available and not os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
        response = test_client.post(f"/vms/{vm_id}/actions/start")
        assert response.status_code == 202
        
        # Wait a bit for VM to start
        time.sleep(2)
        
        # Verify VM is running
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 200
        vm_data = response.json()
        assert vm_data["state"] == "running"
        
        # Stop VM
        response = test_client.post(f"/vms/{vm_id}/actions/stop")
        assert response.status_code == 202
        
        # Wait a bit for VM to stop
        time.sleep(1)
        
        # Verify VM is stopped
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 200
        vm_data = response.json()
        assert vm_data["state"] == "stopped"
    
    # Delete VM (cleanup fixture will handle this, but explicit is good)
    response = test_client.delete(f"/vms/{vm_id}")
    assert response.status_code == 204


@pytest.mark.integration
def test_disk_attach_detach_example(
    test_client: TestClient,
    test_template: dict,
    cleanup_test_vms,
    cleanup_test_disks,
    qemu_available
):
    """Example: Test disk attach/detach with running VM.
    
    This demonstrates testing disk operations with a running VM.
    """
    # Create VM
    response = test_client.post("/vms", json={
        "template_name": test_template["name"],
        "name": "test-vm-disk"
    })
    assert response.status_code == 201
    vm_id = response.json()["id"]
    
    # Create disk
    response = test_client.post("/disks", json={"size": 1})
    assert response.status_code == 201
    disk_id = response.json()["id"]
    
    # Start VM (if QEMU available)
    if qemu_available and not os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(2)
        
        # Attach disk to running VM
        response = test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
        assert response.status_code == 200
        
        # Verify disk is attached
        response = test_client.get(f"/disks/{disk_id}")
        assert response.status_code == 200
        disk_data = response.json()
        assert disk_data["state"] == "attached"
        assert disk_data["vm_id"] == vm_id
        
        # Detach disk
        response = test_client.post(f"/disks/{disk_id}/detach")
        assert response.status_code == 200
        
        # Verify disk is available
        response = test_client.get(f"/disks/{disk_id}")
        assert response.status_code == 200
        disk_data = response.json()
        assert disk_data["state"] == "available"
        assert disk_data["vm_id"] is None
        
        # Stop VM
        test_client.post(f"/vms/{vm_id}/actions/stop")
        time.sleep(1)

