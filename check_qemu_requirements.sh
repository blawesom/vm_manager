#!/bin/bash
echo "Checking QEMU requirements for VMAN testing..."
echo ""

# Check binaries
echo -n "qemu-system-x86_64: "
if which qemu-system-x86_64 > /dev/null 2>&1; then
    echo "✓ ($(which qemu-system-x86_64))"
else
    echo "✗ (not found)"
fi

echo -n "qemu-kvm: "
if which qemu-kvm > /dev/null 2>&1; then
    echo "✓ ($(which qemu-kvm))"
else
    echo "✗ (optional, not found)"
fi

echo -n "qemu-img: "
if which qemu-img > /dev/null 2>&1; then
    echo "✓ ($(which qemu-img))"
    qemu-img --version 2>/dev/null | head -1
else
    echo "✗ (not found)"
fi

# Check architecture
echo -n "Architecture (x86_64): "
if [ "$(uname -m)" = "x86_64" ]; then
    echo "✓ ($(uname -m))"
else
    echo "✗ ($(uname -m) - VMAN only supports x86_64)"
fi

# Check KVM
echo -n "KVM available: "
if [ -c /dev/kvm ]; then
    if [ -r /dev/kvm ] && [ -w /dev/kvm ]; then
        echo "✓ (readable and writable)"
    else
        echo "⚠ (exists but not accessible - add user to kvm group)"
    fi
else
    echo "✗ (not available - will use TCG emulation)"
fi

# Check KVM module
echo -n "KVM module loaded: "
if lsmod | grep -q "^kvm"; then
    echo "✓"
else
    echo "✗ (not loaded)"
fi

# Check CPU virtualization support
echo -n "CPU virtualization support: "
if grep -qE "vmx|svm" /proc/cpuinfo 2>/dev/null; then
    echo "✓"
else
    echo "✗ (not detected)"
fi

# Check dry-run mode
echo -n "Dry-run mode: "
if [ "${VMAN_OPERATOR_DRY_RUN}" = "1" ]; then
    echo "enabled (QEMU will NOT be used)"
else
    echo "disabled (QEMU WILL be used if available)"
fi

echo ""
echo "Summary:"
QEMU_OK=true
if ! which qemu-system-x86_64 > /dev/null 2>&1 && ! which qemu-kvm > /dev/null 2>&1; then
    echo "✗ QEMU system binary not found"
    QEMU_OK=false
fi
if ! which qemu-img > /dev/null 2>&1; then
    echo "✗ qemu-img not found"
    QEMU_OK=false
fi
if [ "$(uname -m)" != "x86_64" ]; then
    echo "✗ Architecture not x86_64"
    QEMU_OK=false
fi

if [ "$QEMU_OK" = true ]; then
    echo "✓ Ready for real QEMU testing"
    echo ""
    echo "To run tests with QEMU:"
    echo "  unset VMAN_OPERATOR_DRY_RUN"
    echo "  pytest tests/test_integration_*.py -v"
else
    echo "⚠ Not ready for real QEMU testing"
    echo ""
    echo "To run tests in dry-run mode (no QEMU needed):"
    echo "  export VMAN_OPERATOR_DRY_RUN=1"
    echo "  pytest tests/test_integration_*.py -v"
fi
