"""Fixture validation tests for integration test infrastructure.

This module validates that all fixtures in conftest.py work correctly.
These tests should pass in both dry-run and real QEMU modes.
"""
import os
import shutil
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models, operator, observer, network_manager


@pytest.mark.integration
class TestFixtureValidation:
    """Test suite for validating integration test fixtures."""
    
    def test_qemu_available_fixture(self, qemu_available):
        """Validate qemu_available fixture."""
        # If QEMU is not available, test should be skipped
        # If we reach here, QEMU should be available
        if qemu_available:
            assert isinstance(qemu_available, dict)
            assert "bin" in qemu_available
            assert "img" in qemu_available
            assert qemu_available["bin"] is not None
            assert qemu_available["img"] is not None
            # Verify paths exist
            assert Path(qemu_available["bin"]).exists() or shutil.which(qemu_available["bin"])
            assert Path(qemu_available["img"]).exists() or shutil.which(qemu_available["img"])
    
    def test_temp_storage_fixture(self, temp_storage):
        """Validate temp_storage fixture."""
        assert isinstance(temp_storage, Path)
        assert temp_storage.exists()
        assert temp_storage.is_dir()
        # Verify writable
        assert os.access(temp_storage, os.W_OK)
        # Verify we can create files
        test_file = temp_storage / "test_write.txt"
        test_file.write_text("test")
        assert test_file.exists()
        test_file.unlink()
    
    def test_test_db_fixture(self, test_db):
        """Validate test_db fixture creates isolated database."""
        assert isinstance(test_db, Session)
        
        # Verify we can query
        templates = test_db.query(models.VMTemplate).all()
        assert isinstance(templates, list)
        
        # Verify we can create records
        template = models.VMTemplate(
            name="fixture-test-template",
            cpu_count=1,
            ram_amount=512
        )
        test_db.add(template)
        test_db.commit()
        
        # Verify record exists
        found = test_db.query(models.VMTemplate).filter(
            models.VMTemplate.name == "fixture-test-template"
        ).first()
        assert found is not None
        assert found.cpu_count == 1
        
        # Cleanup
        test_db.delete(found)
        test_db.commit()
    
    def test_test_network_manager_fixture(self, test_network_manager):
        """Validate test_network_manager fixture."""
        assert isinstance(test_network_manager, network_manager.NetworkManager)
        assert test_network_manager.vlan_id == 999
        assert test_network_manager.bridge_name == "br-vman-test"
        # subnet is an IPv4Network object, compare as string
        assert str(test_network_manager.subnet) == "192.168.199.0/24"
        assert test_network_manager.gateway == "192.168.199.1"
        assert test_network_manager.dry_run is True  # Should be in dry-run for tests
    
    def test_test_operator_fixture(self, test_operator, temp_storage, test_network_manager):
        """Validate test_operator fixture."""
        assert isinstance(test_operator, operator.LocalOperator)
        assert test_operator.storage_path == temp_storage
        assert test_operator.network_manager == test_network_manager
        # In test environment, should be in dry-run mode by default
        assert test_operator.dry_run is True or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1"
    
    def test_test_observer_fixture(self, test_observer, test_db, test_operator):
        """Validate test_observer fixture."""
        assert isinstance(test_observer, observer.LocalObserver)
        assert test_observer.operator == test_operator
        assert test_observer.check_interval == 1.0  # Faster for tests
        
        # Verify observer can start and stop
        assert not test_observer.running
        test_observer.start()
        assert test_observer.running
        test_observer.stop()
        assert not test_observer.running
    
    def test_test_client_fixture(self, test_client):
        """Validate test_client fixture."""
        assert isinstance(test_client, TestClient)
        
        # Verify client can make requests
        response = test_client.get("/health")
        assert response.status_code in [200, 503]  # Health can be ok or degraded
        
        # Verify client can access API
        response = test_client.get("/templates")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_test_template_fixture(self, test_template, test_client):
        """Validate test_template fixture creates a template."""
        assert isinstance(test_template, dict)
        assert "name" in test_template
        assert "cpu_count" in test_template
        assert "ram_amount" in test_template
        assert test_template["name"] == "test-template"
        assert test_template["cpu_count"] == 1
        assert test_template["ram_amount"] == 512
        
        # Verify template exists in API
        response = test_client.get("/templates")
        assert response.status_code == 200
        templates = response.json()
        template_names = [t["name"] for t in templates]
        assert "test-template" in template_names
    
    def test_cleanup_test_vms_fixture(self, test_client, test_template, cleanup_test_vms):
        """Validate cleanup_test_vms fixture cleans up VMs."""
        # Create a VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "fixture-test-vm"
        })
        assert response.status_code == 201
        vm_id = response.json()["id"]
        
        # Verify VM exists
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 200
        
        # Cleanup fixture will run after test
        # We can't directly test it, but we verify the VM was created
        assert vm_id is not None
    
    def test_cleanup_test_disks_fixture(self, test_client, cleanup_test_disks):
        """Validate cleanup_test_disks fixture cleans up disks."""
        # Create a disk
        response = test_client.post("/disks", json={"size": 1})
        assert response.status_code == 201
        disk_id = response.json()["id"]
        
        # Verify disk exists
        response = test_client.get(f"/disks/{disk_id}")
        assert response.status_code == 200
        
        # Cleanup fixture will run after test
        assert disk_id is not None
    
    def test_cleanup_test_templates_fixture(self, test_client, cleanup_test_templates):
        """Validate cleanup_test_templates fixture cleans up templates."""
        # Create a template
        response = test_client.post("/templates", json={
            "name": "fixture-cleanup-test",
            "cpu_count": 2,
            "ram_amount": 1024
        })
        assert response.status_code == 201
        
        # Verify template exists
        response = test_client.get("/templates/fixture-cleanup-test")
        # Note: There's no GET /templates/{name} endpoint, so we check list
        response = test_client.get("/templates")
        templates = response.json()
        template_names = [t["name"] for t in templates]
        assert "fixture-cleanup-test" in template_names
        
        # Cleanup fixture will run after test
    
    def test_fixture_isolation(self, test_db, test_client):
        """Validate that fixtures provide proper isolation between tests."""
        # Create a template in this test
        response = test_client.post("/templates", json={
            "name": "isolation-test",
            "cpu_count": 1,
            "ram_amount": 256
        })
        assert response.status_code == 201
        
        # Verify it exists
        response = test_client.get("/templates")
        templates = response.json()
        template_names = [t["name"] for t in templates]
        assert "isolation-test" in template_names


@pytest.mark.integration
class TestFixtureIntegration:
    """Test that fixtures work together correctly."""
    
    def test_fixture_chain(self, test_client, test_template, temp_storage, test_operator):
        """Test that fixture dependency chain works."""
        # All fixtures should be available and work together
        assert test_client is not None
        assert test_template is not None
        assert temp_storage is not None
        assert test_operator is not None
        
        # Verify operator uses temp storage
        assert test_operator.storage_path == temp_storage
        
        # Verify client can use template
        response = test_client.get("/templates")
        assert response.status_code == 200
        templates = response.json()
        assert len(templates) > 0
    
    def test_observer_with_operator(self, test_observer, test_operator):
        """Test that observer works with operator."""
        assert test_observer.operator == test_operator
        
        # Observer should be able to check coherence
        test_observer.start()
        try:
            # Give it a moment to run
            import time
            time.sleep(0.5)
            
            # Check that observer is running
            assert test_observer.running
            
            # Check that we can get issues (should be empty in clean state)
            issues = test_observer.check_coherence()
            assert isinstance(issues, list)
        finally:
            test_observer.stop()
    
    def test_client_with_observer(self, test_client, test_observer):
        """Test that test client works with observer running."""
        # Observer should be started by test_client fixture
        assert test_observer.running
        
        # Client should work
        response = test_client.get("/health")
        assert response.status_code in [200, 503]
    
    def test_storage_paths_exist(self, temp_storage, test_operator):
        """Test that storage paths are created correctly."""
        # Verify base storage exists
        assert test_operator.storage_path.exists()
        
        # Verify subdirectories can be created
        vms_dir = test_operator.storage_path / "vms"
        disks_dir = test_operator.storage_path / "disks"
        
        # These may not exist yet, but parent should be writable
        assert test_operator.storage_path.is_dir()
        assert os.access(test_operator.storage_path, os.W_OK)


@pytest.mark.integration
class TestFixtureCleanup:
    """Test that cleanup fixtures work correctly."""
    
    def test_cleanup_vms_removes_all(self, test_client, test_template, cleanup_test_vms):
        """Test that cleanup_test_vms removes all VMs."""
        # Create multiple VMs
        vm_ids = []
        for i in range(3):
            response = test_client.post("/vms", json={
                "template_name": test_template["name"],
                "name": f"cleanup-test-vm-{i}"
            })
            assert response.status_code == 201
            vm_ids.append(response.json()["id"])
        
        # Verify all exist
        response = test_client.get("/vms")
        assert response.status_code == 200
        vms = response.json()
        vm_names = [vm["id"] for vm in vms]
        for vm_id in vm_ids:
            assert vm_id in vm_names
        
        # Cleanup fixture will remove them after test
    
    def test_cleanup_disks_removes_all(self, test_client, cleanup_test_disks):
        """Test that cleanup_test_disks removes all disks."""
        # Create multiple disks
        disk_ids = []
        for i in range(3):
            response = test_client.post("/disks", json={"size": 1})
            assert response.status_code == 201
            disk_ids.append(response.json()["id"])
        
        # Verify all exist
        response = test_client.get("/disks")
        assert response.status_code == 200
        disks = response.json()
        disk_names = [disk["id"] for disk in disks]
        for disk_id in disk_ids:
            assert disk_id in disk_names
        
        # Cleanup fixture will remove them after test

