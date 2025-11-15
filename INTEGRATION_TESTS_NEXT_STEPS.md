# Integration Tests - Next Steps

## Quick Start

You now have the foundation for integration tests. Here's what's been created and what to do next.

## ✅ What's Been Created

1. **`docs/INTEGRATION_TESTS_PLAN.md`** - Comprehensive plan with all test scenarios
2. **`tests/conftest.py`** - Shared fixtures for all integration tests
3. **`tests/test_integration_example.py`** - Example integration tests showing the pattern

## 🚀 Immediate Next Steps

### Step 1: Verify Setup (5 minutes)

Test that the fixtures work:

```bash
# Run the example integration test (will skip if QEMU not available)
pytest tests/test_integration_example.py -v

# Check if QEMU is detected
pytest tests/test_integration_example.py::test_vm_lifecycle_example -v -s
```

### Step 2: Create First Real Integration Test (30 minutes)

Create `tests/test_integration_vm_lifecycle.py` based on the example:

```python
import pytest
import time
from fastapi.testclient import TestClient

@pytest.mark.integration
def test_create_and_start_vm(test_client, test_template, cleanup_test_vms, qemu_available):
    """Test creating and starting a VM with real QEMU."""
    # Your test code here
    pass
```

### Step 3: Test Infrastructure Validation (15 minutes)

Verify all fixtures work correctly:

```bash
# Test with dry-run (no QEMU needed)
export VMAN_OPERATOR_DRY_RUN=1
pytest tests/test_integration_example.py -v

# Test with real QEMU (if available)
unset VMAN_OPERATOR_DRY_RUN
pytest tests/test_integration_example.py -v
```

## 📋 Implementation Checklist

### Phase 1: Foundation ✅
- [x] Create integration test plan
- [x] Create `conftest.py` with fixtures
- [x] Create example integration test
- [ ] Test fixtures work correctly
- [ ] Fix any fixture issues

### Phase 2: Core Tests (Next Priority)
- [ ] Create `test_integration_vm_lifecycle.py`
  - [ ] Test VM create → start → stop → delete
  - [ ] Test VM restart
  - [ ] Test VM error handling
- [ ] Create `test_integration_disks.py`
  - [ ] Test disk create → attach → detach → delete
  - [ ] Test disk hot-plugging
- [ ] Verify cleanup works correctly

### Phase 3: Advanced Tests
- [ ] Create `test_integration_observer.py`
- [ ] Create `test_integration_network.py` (if network privileges available)
- [ ] Create `test_integration_e2e.py`

## 🛠️ Common Tasks

### Running Integration Tests

```bash
# Run all integration tests
pytest -m integration

# Run specific integration test file
pytest tests/test_integration_vm_lifecycle.py -v

# Skip integration tests (unit tests only)
pytest -m "not integration"

# Run with coverage
pytest -m integration --cov=app --cov-report=term
```

### Debugging Integration Tests

```bash
# Run with verbose output and print statements
pytest tests/test_integration_example.py -v -s

# Run single test
pytest tests/test_integration_example.py::test_vm_lifecycle_example -v -s

# Run with debugger (pdb)
pytest tests/test_integration_example.py --pdb
```

## 📝 Writing New Integration Tests

### Template

```python
import pytest
from fastapi.testclient import TestClient

@pytest.mark.integration
def test_your_scenario(
    test_client: TestClient,
    test_template: dict,
    cleanup_test_vms,
    cleanup_test_disks,
    qemu_available
):
    """Test description."""
    # 1. Setup
    # 2. Execute
    # 3. Verify
    # Cleanup handled by fixtures
    pass
```

### Best Practices

1. **Always use cleanup fixtures** - `cleanup_test_vms`, `cleanup_test_disks`, etc.
2. **Check QEMU availability** - Use `qemu_available` fixture
3. **Add timeouts** - Use `pytest-timeout` for long-running tests
4. **Test both success and failure** - Test error cases too
5. **Use descriptive names** - `test_create_vm_then_start_then_stop`

## 🔧 Troubleshooting

### Fixtures Not Working

If fixtures aren't found:
```bash
# Ensure conftest.py is in tests/ directory
ls tests/conftest.py

# Check pytest can find it
pytest --fixtures | grep test_client
```

### QEMU Not Detected

```bash
# Check if QEMU is installed
which qemu-system-x86_64
which qemu-img

# Test will skip automatically if not found
```

### Database Conflicts

If you see database errors:
- Each test gets its own isolated database
- Check that `test_db` fixture is being used
- Verify cleanup is working

### Storage Issues

If storage tests fail:
- Check `temp_storage` fixture creates directory
- Verify sufficient disk space
- Check permissions on temp directory

## 📚 Reference

- **Full Plan**: See `docs/INTEGRATION_TESTS_PLAN.md`
- **Example Tests**: See `tests/test_integration_example.py`
- **Fixtures**: See `tests/conftest.py`

## 🎯 Success Metrics

Integration tests are ready when:

- [ ] At least 3 integration test files exist
- [ ] VM lifecycle fully tested
- [ ] Disk operations fully tested
- [ ] All tests pass consistently
- [ ] Tests can run in CI/CD
- [ ] Documentation updated

## 💡 Tips

1. **Start Small**: Begin with one simple integration test
2. **Iterate**: Add more tests as you go
3. **Use Dry-Run**: Test infrastructure without QEMU first
4. **Clean Up**: Always verify cleanup works
5. **Document**: Add docstrings explaining what each test validates

---

**Ready to start?** Begin with Step 1 above and create your first real integration test!

