# Integration Tests Preparation Plan

## Overview

This document outlines the steps to prepare and implement integration tests for the VMAN system. Integration tests will validate end-to-end workflows involving real QEMU operations, database interactions, and service coordination.

## Current State

- ✅ Unit tests exist for API endpoints (mocked)
- ✅ Test infrastructure (pytest, markers) is in place
- ✅ Dry-run mode available for testing without QEMU
- ❌ No integration tests with real QEMU
- ❌ No shared test fixtures (conftest.py)
- ❌ No test isolation/cleanup infrastructure

## Goals

1. **Test Real VM Lifecycle**: Create, start, stop, restart, delete VMs with actual QEMU
2. **Test Disk Operations**: Create, attach, detach disks with running VMs
3. **Test Observer Coherence**: Verify observer detects and reports inconsistencies
4. **Test Network Integration**: Validate network configuration and IP assignment
5. **Test Error Recovery**: Verify system handles failures gracefully

---

## Step 1: Create Shared Test Infrastructure

### 1.1 Create `tests/conftest.py`

**Purpose**: Shared fixtures for all integration tests

**Key Fixtures Needed**:
- `temp_storage`: Temporary directory for VM/disk storage
- `test_db`: Isolated test database
- `test_operator`: Operator instance with test storage
- `test_network_manager`: Network manager for integration tests
- `test_observer`: Observer instance for testing
- `test_client`: FastAPI test client with real services
- `qemu_available`: Skip marker if QEMU not available

**Implementation Priority**: **HIGH** (Foundation for all other tests)

---

## Step 2: Test Environment Setup

### 2.1 QEMU Detection and Validation

**Tasks**:
- Check if `qemu-system-x86_64` or `qemu-kvm` is available
- Check if `qemu-img` is available
- Validate QEMU version compatibility
- Check for KVM support (optional, TCG fallback)

**Implementation**:
```python
@pytest.fixture(scope="session")
def qemu_available():
    """Check if QEMU is available for integration tests."""
    qemu_bin = shutil.which("qemu-system-x86_64") or shutil.which("qemu-kvm")
    qemu_img = shutil.which("qemu-img")
    if not qemu_bin or not qemu_img:
        pytest.skip("QEMU not available for integration tests")
    return {"bin": qemu_bin, "img": qemu_img}
```

### 2.2 Test Storage Management

**Tasks**:
- Create temporary storage directory for each test run
- Cleanup after tests complete
- Ensure sufficient disk space
- Handle concurrent test execution

**Implementation**:
```python
@pytest.fixture(scope="session")
def temp_storage(tmp_path_factory):
    """Create temporary storage directory for integration tests."""
    storage = tmp_path_factory.mktemp("vman_test_storage")
    yield storage
    # Cleanup handled by tmp_path_factory
```

### 2.3 Test Database Isolation

**Tasks**:
- Create isolated test database per test session
- Ensure clean state between tests
- Support parallel test execution

---

## Step 3: Integration Test Scenarios

### 3.1 VM Lifecycle Integration Tests

**File**: `tests/test_integration_vm_lifecycle.py`

**Test Scenarios**:
1. **Create and Start VM**
   - Create template
   - Create VM from template
   - Start VM
   - Verify QEMU process exists
   - Verify VM state in database is "running"
   - Verify IP assignment (if network enabled)

2. **Stop Running VM**
   - Start VM
   - Stop VM
   - Verify QEMU process terminated
   - Verify VM state is "stopped"
   - Verify resources cleaned up

3. **Restart VM**
   - Start VM
   - Restart VM
   - Verify VM restarted successfully
   - Verify state transitions correctly

4. **Delete VM**
   - Create and start VM
   - Delete VM
   - Verify QEMU process terminated
   - Verify VM removed from database
   - Verify storage cleaned up

5. **VM Error Handling**
   - Start VM with invalid configuration
   - Verify error state set
   - Verify cleanup on error

**Priority**: **HIGH**

---

### 3.2 Disk Operations Integration Tests

**File**: `tests/test_integration_disks.py`

**Test Scenarios**:
1. **Create and Attach Disk to Running VM**
   - Create VM and start it
   - Create disk
   - Attach disk to running VM
   - Verify disk attached via QMP
   - Verify disk state is "attached"
   - Verify mount point set

2. **Detach Disk from Running VM**
   - Attach disk to running VM
   - Detach disk
   - Verify disk detached via QMP
   - Verify disk state is "available"
   - Verify mount point cleared

3. **Disk Hot-Plugging**
   - Start VM
   - Attach disk while VM running
   - Detach disk while VM running
   - Verify no VM interruption

4. **Delete Attached Disk**
   - Attach disk to VM
   - Stop VM
   - Delete disk
   - Verify disk file removed
   - Verify database record removed

**Priority**: **HIGH**

---

### 3.3 Observer Coherence Integration Tests

**File**: `tests/test_integration_observer.py`

**Test Scenarios**:
1. **Detect VM State Mismatch**
   - Create VM in database with state "running"
   - Don't actually start QEMU process
   - Run observer check
   - Verify mismatch detected

2. **Detect Orphan QEMU Process**
   - Start QEMU process manually (outside API)
   - Run observer check
   - Verify orphan process detected

3. **Detect Missing Disk File**
   - Create disk in database
   - Delete disk file manually
   - Run observer check
   - Verify missing disk detected

4. **Detect Orphan Disk File**
   - Create disk file manually (outside API)
   - Run observer check
   - Verify orphan file detected

5. **Observer Periodic Checks**
   - Start observer
   - Create inconsistency
   - Wait for check interval
   - Verify issue detected

**Priority**: **MEDIUM**

---

### 3.4 Network Integration Tests

**File**: `tests/test_integration_network.py`

**Test Scenarios**:
1. **IP Assignment on VM Start**
   - Configure network manager
   - Start VM
   - Verify IP assigned
   - Verify IP in database

2. **IP Release on VM Stop**
   - Start VM with assigned IP
   - Stop VM
   - Verify IP released
   - Verify IP available for reuse

3. **Network Configuration**
   - Get network config
   - Verify VLAN, bridge, subnet settings
   - Verify allocated IPs list

**Priority**: **MEDIUM** (requires network privileges)

---

### 3.5 End-to-End Workflow Tests

**File**: `tests/test_integration_e2e.py`

**Test Scenarios**:
1. **Complete VM Workflow**
   - Create template
   - Create VM
   - Create disk
   - Start VM
   - Attach disk
   - Verify everything works
   - Detach disk
   - Stop VM
   - Delete disk
   - Delete VM
   - Delete template

2. **Multiple VMs Concurrent**
   - Create multiple VMs
   - Start all VMs
   - Verify all running
   - Stop all VMs
   - Cleanup

3. **Error Recovery**
   - Start VM
   - Kill QEMU process manually
   - Run observer check
   - Verify error detected
   - Restart VM
   - Verify recovery

**Priority**: **HIGH**

---

## Step 4: Test Infrastructure Components

### 4.1 Required Files

1. **`tests/conftest.py`** - Shared fixtures
2. **`tests/test_integration_vm_lifecycle.py`** - VM lifecycle tests
3. **`tests/test_integration_disks.py`** - Disk operation tests
4. **`tests/test_integration_observer.py`** - Observer coherence tests
5. **`tests/test_integration_network.py`** - Network integration tests
6. **`tests/test_integration_e2e.py`** - End-to-end workflow tests

### 4.2 Test Utilities

**File**: `tests/integration_utils.py`

**Helper Functions**:
- `wait_for_vm_state()` - Wait for VM to reach expected state
- `verify_qemu_process()` - Check if QEMU process exists
- `verify_disk_file()` - Check if disk file exists
- `cleanup_test_resources()` - Cleanup test artifacts
- `create_test_template()` - Helper to create test template

---

## Step 5: Implementation Roadmap

### Phase 1: Foundation (2-3 hours)
- [ ] Create `tests/conftest.py` with basic fixtures
- [ ] Implement QEMU detection and validation
- [ ] Set up test storage management
- [ ] Create test database isolation
- [ ] Add integration test utilities

### Phase 2: Core Integration Tests (3-4 hours)
- [ ] Implement VM lifecycle integration tests
- [ ] Implement disk operations integration tests
- [ ] Add proper cleanup and teardown
- [ ] Test error handling scenarios

### Phase 3: Advanced Integration Tests (2-3 hours)
- [ ] Implement observer coherence tests
- [ ] Implement network integration tests (if possible)
- [ ] Implement end-to-end workflow tests

### Phase 4: CI/CD Integration (1 hour)
- [ ] Add integration test markers
- [ ] Configure CI to run integration tests conditionally
- [ ] Document how to run integration tests locally
- [ ] Add integration test requirements to README

---

## Step 6: Test Execution Strategy

### 6.1 Local Development

```bash
# Run all integration tests (requires QEMU)
pytest -m integration

# Run specific integration test file
pytest tests/test_integration_vm_lifecycle.py -v

# Run integration tests with coverage
pytest -m integration --cov=app --cov-report=term

# Skip integration tests (unit tests only)
pytest -m "not integration"
```

### 6.2 CI/CD Pipeline

**Option 1: Conditional Execution**
- Check for QEMU availability
- Skip integration tests if QEMU not available
- Run unit tests always

**Option 2: Separate Integration Test Job**
- Create separate CI job for integration tests
- Run on dedicated runner with QEMU
- Mark as non-blocking for PRs

### 6.3 Test Isolation

- Each test should be independent
- Use fixtures for setup/teardown
- Clean up resources after each test
- Use unique VM/disk IDs to avoid conflicts

---

## Step 7: Dependencies and Requirements

### 7.1 Additional Test Dependencies

Add to `requirements.txt` or `requirements-dev.txt`:
```
pytest>=7.0
pytest-cov>=4.0
pytest-xdist>=3.0  # For parallel test execution
pytest-timeout>=2.0  # For test timeouts
```

### 7.2 System Requirements

- QEMU installed (`qemu-system-x86_64` or `qemu-kvm`)
- `qemu-img` available
- Sufficient disk space (at least 1GB free)
- Optional: KVM support (for faster tests)
- Optional: Network privileges (for network tests)

### 7.3 Environment Variables

```bash
# Enable integration tests
export VMAN_ENABLE_INTEGRATION_TESTS=1

# Use test storage directory
export VMAN_STORAGE_PATH=/tmp/vman_test_storage

# Disable dry-run for integration tests
unset VMAN_OPERATOR_DRY_RUN
```

---

## Step 8: Documentation Updates

### 8.1 Update `tests/README.md`

Add section for integration tests:
- How to run integration tests
- Prerequisites
- Troubleshooting
- CI/CD integration

### 8.2 Update `PROJECT_STATUS.md`

- Mark integration tests as in progress
- Update coverage goals
- Document test execution times

---

## Step 9: Test Data and Fixtures

### 9.1 Test Templates

Create standard test templates:
- `small`: 1 CPU, 512MB RAM (for fast tests)
- `medium`: 2 CPU, 1GB RAM (for standard tests)
- `large`: 4 CPU, 2GB RAM (for stress tests)

### 9.2 Test Disks

Standard test disk sizes:
- `1GB`: Small test disk
- `5GB`: Medium test disk
- `10GB`: Large test disk

---

## Step 10: Success Criteria

Integration tests are considered complete when:

- [ ] All core VM lifecycle scenarios tested
- [ ] Disk attach/detach operations tested
- [ ] Observer coherence detection tested
- [ ] Error handling and recovery tested
- [ ] Tests can run in CI/CD pipeline
- [ ] Test execution time < 10 minutes
- [ ] All tests pass consistently
- [ ] Documentation updated

---

## Next Steps

1. **Start with Step 1**: Create `tests/conftest.py` with basic fixtures
2. **Implement Phase 1**: Set up test infrastructure
3. **Implement Phase 2**: Create core integration tests
4. **Iterate**: Add more test scenarios as needed

---

## Notes

- Integration tests should be marked with `@pytest.mark.integration`
- Tests should skip gracefully if QEMU not available
- Use timeouts to prevent hanging tests
- Clean up resources even on test failure
- Consider using Docker for CI/CD integration tests

