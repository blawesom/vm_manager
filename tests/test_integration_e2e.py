"""End-to-end integration tests for complete workflows.

Tests complete workflows that combine multiple operations:
- Full VM lifecycle with disks
- Multiple concurrent VMs
- Error recovery scenarios
"""
import os
import pytest
import time
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.timeout(600)
class TestEndToEndWorkflows:
    """Test complete end-to-end workflows."""
    
    def test_complete_vm_workflow(self, test_client: TestClient, test_template: dict,
                                  cleanup_test_vms, cleanup_test_disks, cleanup_test_templates, qemu_available):
        """Test complete workflow: template -> VM -> disk -> start -> attach -> detach -> stop -> delete."""
        # 1. Template already exists (from fixture)
        assert test_template is not None
        
        # 2. Create VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "e2e-vm-workflow"
        })
        assert response.status_code == 201
        vm_id = response.json()["id"]
        assert response.json()["state"] == "stopped"
        
        # 3. Create disk
        response = test_client.post("/disks", json={"size": 2})
        assert response.status_code == 201
        disk_id = response.json()["id"]
        assert response.json()["state"] == "available"
        
        # 4. Start VM (if QEMU available)
        if qemu_available and not os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            response = test_client.post(f"/vms/{vm_id}/actions/start")
            assert response.status_code == 202
            time.sleep(3)
            
            # Verify VM is running
            response = test_client.get(f"/vms/{vm_id}")
            assert response.json()["state"] == "running"
            
            # 5. Attach disk
            response = test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
            assert response.status_code == 200
            
            # Verify disk is attached
            response = test_client.get(f"/disks/{disk_id}")
            assert response.json()["state"] == "attached"
            assert response.json()["vm_id"] == vm_id
            
            # 6. Detach disk
            response = test_client.post(f"/disks/{disk_id}/detach")
            assert response.status_code == 200
            
            # Verify disk is available
            response = test_client.get(f"/disks/{disk_id}")
            assert response.json()["state"] == "available"
            
            # 7. Stop VM
            response = test_client.post(f"/vms/{vm_id}/actions/stop")
            assert response.status_code == 202
            time.sleep(2)
            
            # Verify VM is stopped
            response = test_client.get(f"/vms/{vm_id}")
            assert response.json()["state"] == "stopped"
        
        # 8. Delete disk
        response = test_client.delete(f"/disks/{disk_id}")
        assert response.status_code == 204
        
        # Verify disk is gone
        response = test_client.get(f"/disks/{disk_id}")
        assert response.status_code == 404
        
        # 9. Delete VM
        response = test_client.delete(f"/vms/{vm_id}")
        assert response.status_code == 204
        
        # Verify VM is gone
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 404
    
    def test_multiple_vms_concurrent(self, test_client: TestClient, test_template: dict,
                                     cleanup_test_vms, qemu_available):
        """Test creating and managing multiple VMs concurrently."""
        # Create multiple VMs
        vm_ids = []
        for i in range(3):
            response = test_client.post("/vms", json={
                "template_name": test_template["name"],
                "name": f"e2e-vm-concurrent-{i}"
            })
            assert response.status_code == 201
            vm_ids.append(response.json()["id"])
        
        # Verify all VMs exist
        response = test_client.get("/vms")
        assert response.status_code == 200
        all_vms = response.json()
        vm_names = [vm["id"] for vm in all_vms]
        for vm_id in vm_ids:
            assert vm_id in vm_names
        
        # Start all VMs (if QEMU available)
        if qemu_available and not os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            for vm_id in vm_ids:
                response = test_client.post(f"/vms/{vm_id}/actions/start")
                assert response.status_code == 202
            
            # Wait for all to start
            time.sleep(5)
            
            # Verify all are running
            for vm_id in vm_ids:
                response = test_client.get(f"/vms/{vm_id}")
                assert response.json()["state"] == "running"
            
            # Stop all VMs
            for vm_id in vm_ids:
                response = test_client.post(f"/vms/{vm_id}/actions/stop")
                assert response.status_code == 202
            
            # Wait for all to stop
            time.sleep(3)
            
            # Verify all are stopped
            for vm_id in vm_ids:
                response = test_client.get(f"/vms/{vm_id}")
                assert response.json()["state"] == "stopped"
        
        # Delete all VMs (cleanup fixture will handle, but explicit is good)
        for vm_id in vm_ids:
            response = test_client.delete(f"/vms/{vm_id}")
            assert response.status_code == 204
    
    def test_vm_with_multiple_disks(self, test_client: TestClient, test_template: dict,
                                    cleanup_test_vms, cleanup_test_disks, qemu_available):
        """Test VM with multiple disks attached."""
        # Create VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "e2e-vm-multi-disk"
        })
        vm_id = response.json()["id"]
        
        # Create multiple disks
        disk_ids = []
        for i in range(3):
            response = test_client.post("/disks", json={"size": 1})
            assert response.status_code == 201
            disk_ids.append(response.json()["id"])
        
        # Start VM (if QEMU available)
        if qemu_available and not os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            test_client.post(f"/vms/{vm_id}/actions/start")
            time.sleep(3)
            
            # Attach all disks
            for disk_id in disk_ids:
                response = test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
                assert response.status_code == 200
                time.sleep(0.5)
            
            # Verify all disks are attached
            for disk_id in disk_ids:
                response = test_client.get(f"/disks/{disk_id}")
                assert response.json()["state"] == "attached"
                assert response.json()["vm_id"] == vm_id
            
            # Detach all disks
            for disk_id in disk_ids:
                response = test_client.post(f"/disks/{disk_id}/detach")
                assert response.status_code == 200
                time.sleep(0.5)
            
            # Verify all disks are available
            for disk_id in disk_ids:
                response = test_client.get(f"/disks/{disk_id}")
                assert response.json()["state"] == "available"
            
            # Stop VM
            test_client.post(f"/vms/{vm_id}/actions/stop")
            time.sleep(2)
    
    def test_template_vm_disk_chain(self, test_client: TestClient, cleanup_test_vms, cleanup_test_disks, cleanup_test_templates):
        """Test creating template, VM, and disk in sequence."""
        # 1. Create template
        response = test_client.post("/templates", json={
            "name": "e2e-template-chain",
            "cpu_count": 2,
            "ram_amount": 1024
        })
        assert response.status_code == 201
        template_name = response.json()["name"]
        
        # 2. Create VM from template
        response = test_client.post("/vms", json={
            "template_name": template_name,
            "name": "e2e-vm-chain"
        })
        assert response.status_code == 201
        vm_id = response.json()["id"]
        
        # 3. Create disk
        response = test_client.post("/disks", json={"size": 5})
        assert response.status_code == 201
        disk_id = response.json()["id"]
        
        # Verify all resources exist
        response = test_client.get(f"/templates/{template_name}")
        # Note: GET /templates/{name} may not exist, so check list
        response = test_client.get("/templates")
        templates = response.json()
        assert any(t["name"] == template_name for t in templates)
        
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 200
        
        response = test_client.get(f"/disks/{disk_id}")
        assert response.status_code == 200
    
    def test_error_recovery_workflow(self, test_client: TestClient, test_template: dict,
                                    cleanup_test_vms, test_observer, qemu_available):
        """Test error recovery: create inconsistency, detect it, fix it."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create and start VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "e2e-vm-recovery"
        })
        vm_id = response.json()["id"]
        
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        
        # Verify VM is running
        response = test_client.get(f"/vms/{vm_id}")
        assert response.json()["state"] == "running"
        
        # Manually set state to "stopped" in DB to create inconsistency
        from app import models, db
        db_session = db.SessionLocal()
        try:
            vm = db_session.query(models.VM).filter(models.VM.id == vm_id).first()
            vm.state = "stopped"
            db_session.commit()
        finally:
            db_session.close()
        
        # Run observer check
        issues = test_observer.check_coherence()
        
        # Should detect mismatch
        vm_issues = [i for i in issues if i.resource_id == vm_id]
        assert len(vm_issues) > 0
        assert any(i.issue_type == "vm_state_mismatch" for i in vm_issues)
        
        # Fix: Restart VM (which will sync state)
        test_client.post(f"/vms/{vm_id}/actions/restart")
        time.sleep(4)
        
        # Verify VM is running again
        response = test_client.get(f"/vms/{vm_id}")
        assert response.json()["state"] == "running"
        
        # Run observer check again
        issues = test_observer.check_coherence()
        vm_issues = [i for i in issues if i.resource_id == vm_id]
        # Should have no issues now (or at least not the mismatch)
        mismatch_issues = [i for i in vm_issues if i.issue_type == "vm_state_mismatch"]
        assert len(mismatch_issues) == 0
        
        # Cleanup
        test_client.post(f"/vms/{vm_id}/actions/stop")
        time.sleep(2)
    
    def test_list_all_resources(self, test_client: TestClient, test_template: dict,
                                cleanup_test_vms, cleanup_test_disks):
        """Test listing all resources (templates, VMs, disks)."""
        # Create some resources
        vm_ids = []
        for i in range(2):
            response = test_client.post("/vms", json={
                "template_name": test_template["name"],
                "name": f"e2e-list-vm-{i}"
            })
            vm_ids.append(response.json()["id"])
        
        disk_ids = []
        for i in range(2):
            response = test_client.post("/disks", json={"size": 1})
            disk_ids.append(response.json()["id"])
        
        # List templates
        response = test_client.get("/templates")
        assert response.status_code == 200
        templates = response.json()
        assert len(templates) > 0
        
        # List VMs
        response = test_client.get("/vms")
        assert response.status_code == 200
        vms = response.json()
        vm_names = [vm["id"] for vm in vms]
        for vm_id in vm_ids:
            assert vm_id in vm_names
        
        # List disks
        response = test_client.get("/disks")
        assert response.status_code == 200
        disks = response.json()
        disk_names = [disk["id"] for disk in disks]
        for disk_id in disk_ids:
            assert disk_id in disk_names
    
    def test_filtered_listing(self, test_client: TestClient, test_template: dict, cleanup_test_vms):
        """Test filtered resource listing."""
        # Create VMs
        for i in range(3):
            test_client.post("/vms", json={
                "template_name": test_template["name"],
                "name": f"e2e-filter-vm-{i}"
            })
        
        # List stopped VMs
        response = test_client.get("/vms?state=stopped")
        assert response.status_code == 200
        stopped_vms = response.json()
        assert len(stopped_vms) >= 3
        assert all(vm["state"] == "stopped" for vm in stopped_vms)
        
        # List running VMs (should be empty)
        response = test_client.get("/vms?state=running")
        assert response.status_code == 200
        running_vms = response.json()
        assert all(vm["state"] == "running" for vm in running_vms) if running_vms else True

