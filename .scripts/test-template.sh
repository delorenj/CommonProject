#!/usr/bin/env bash
# Test script for validating the Copier template

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$(dirname "$SCRIPT_DIR")"
TEST_OUTPUT_DIR="/tmp/copier-template-test"

echo "🧪 Testing Copier Template"
echo "Template: $TEMPLATE_DIR"
echo "Output: $TEST_OUTPUT_DIR"
echo ""

# Check if copier is installed
if ! command -v copier &> /dev/null; then
    echo "❌ Copier not found. Install with: uv tool install copier"
    exit 1
fi

# Clean previous test output
if [ -d "$TEST_OUTPUT_DIR" ]; then
    echo "🧹 Cleaning previous test output..."
    rm -rf "$TEST_OUTPUT_DIR"
fi

mkdir -p "$TEST_OUTPUT_DIR"

# Test 1: Software Project (Python)
echo "📦 Test 1: Python Software Project"
copier copy "$TEMPLATE_DIR" "$TEST_OUTPUT_DIR/test-python-service" \
    --data project_name="Test Python Service" \
    --data project_type=software \
    --data primary_language=python \
    --data plane_workspace=33god \
    --data plane_project_id=1234567890 \
    --data project_identifier=TPS \
    --data uses_docker=true \
    --data uses_event_bus=true \
    --data additional_services="postgres,redis" \
    --data initialize_god_docs=true \
    --data component_domain=infrastructure \
    --defaults

# Validate generated files
if [ -f "$TEST_OUTPUT_DIR/test-python-service/CLAUDE.md" ] && \
   [ -f "$TEST_OUTPUT_DIR/test-python-service/mise.toml" ] && \
   [ -f "$TEST_OUTPUT_DIR/test-python-service/docker-compose.yml" ]; then
    echo "✅ Python service generated successfully"
else
    echo "❌ Python service generation failed"
    exit 1
fi

# Test 2: Hardware Project
echo ""
echo "🔧 Test 2: Hardware Project"
copier copy "$TEMPLATE_DIR" "$TEST_OUTPUT_DIR/test-hardware-device" \
    --data project_name="Test Hardware Device" \
    --data project_type=hardware \
    --data has_hardware=true \
    --data hardware_platform="Raspberry Pi 4" \
    --data hardware_hostname="testdevice.local" \
    --data hardware_peripherals="Camera Module, Temperature Sensor" \
    --data has_agent=true \
    --data agent_name="TestBot" \
    --data agent_role="Hardware Controller" \
    --data primary_language=python \
    --data plane_workspace=33god \
    --data plane_project_id=9876543210 \
    --data project_identifier=THD \
    --data uses_docker=false \
    --data uses_event_bus=true \
    --data initialize_god_docs=true \
    --data component_domain=custom \
    --defaults

if [ -f "$TEST_OUTPUT_DIR/test-hardware-device/CLAUDE.md" ]; then
    # Verify hardware-specific content
    if grep -q "Raspberry Pi 4" "$TEST_OUTPUT_DIR/test-hardware-device/CLAUDE.md"; then
        echo "✅ Hardware project generated with correct hardware details"
    else
        echo "❌ Hardware project missing hardware details"
        exit 1
    fi
else
    echo "❌ Hardware project generation failed"
    exit 1
fi

# Test 3: TypeScript Dashboard
echo ""
echo "🎨 Test 3: TypeScript Dashboard"
copier copy "$TEMPLATE_DIR" "$TEST_OUTPUT_DIR/test-dashboard" \
    --data project_name="Test Dashboard" \
    --data project_type=dashboard \
    --data primary_language=typescript \
    --data plane_workspace=33god \
    --data plane_project_id=5555555555 \
    --data project_identifier=TDB \
    --data uses_docker=true \
    --data uses_event_bus=true \
    --data initialize_god_docs=true \
    --data component_domain=dashboards-voice \
    --defaults

if [ -f "$TEST_OUTPUT_DIR/test-dashboard/CLAUDE.md" ] && \
   [ -f "$TEST_OUTPUT_DIR/test-dashboard/docker-compose.yml" ]; then
    echo "✅ Dashboard project generated successfully"
else
    echo "❌ Dashboard project generation failed"
    exit 1
fi

# Test 4: Rust CLI Tool
echo ""
echo "⚙️  Test 4: Rust CLI Tool"
copier copy "$TEMPLATE_DIR" "$TEST_OUTPUT_DIR/test-cli-tool" \
    --data project_name="Test CLI Tool" \
    --data project_type=tooling \
    --data primary_language=rust \
    --data plane_workspace=33god \
    --data plane_project_id=7777777777 \
    --data project_identifier=TCT \
    --data uses_docker=false \
    --data uses_event_bus=false \
    --data initialize_god_docs=false \
    --defaults

if [ -f "$TEST_OUTPUT_DIR/test-cli-tool/CLAUDE.md" ]; then
    echo "✅ CLI tool generated successfully"
else
    echo "❌ CLI tool generation failed"
    exit 1
fi

# Summary
echo ""
echo "✨ All tests passed!"
echo ""
echo "📁 Generated projects:"
echo "  1. $TEST_OUTPUT_DIR/test-python-service"
echo "  2. $TEST_OUTPUT_DIR/test-hardware-device"
echo "  3. $TEST_OUTPUT_DIR/test-dashboard"
echo "  4. $TEST_OUTPUT_DIR/test-cli-tool"
echo ""
echo "🔍 Review generated projects to validate template correctness"
echo "🧹 Clean up with: rm -rf $TEST_OUTPUT_DIR"
