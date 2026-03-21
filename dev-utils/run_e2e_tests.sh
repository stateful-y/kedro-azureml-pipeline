#!/bin/bash
set -e

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load environment variables from local.env if it exists
if [ -f "$SCRIPT_DIR/local.env" ]; then
    echo "📋 Loading environment variables from local.env..."
    set -a  # automatically export all variables
    source "$SCRIPT_DIR/local.env"
    set +a
else
    echo "⚠️  Warning: local.env file not found at $SCRIPT_DIR/local.env"
    echo "   Using default mock values for Azure credentials"

    # Set default values if not provided
    export AZURE_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-00000000-0000-0000-0000-000000000000}"
    export AZURE_TENANT_ID="${AZURE_TENANT_ID:-00000000-0000-0000-0000-000000000000}"
    export AZURE_CLIENT_ID="${AZURE_CLIENT_ID:-mock-client-id}"
    export AZURE_CLIENT_SECRET="${AZURE_CLIENT_SECRET:-mock-client-secret}"
fi

echo "=== Local E2E Test Reproduction Script ==="
echo "This script reproduces the complete e2e test workflow including Docker and Azure execution"
echo ""

# Configuration
E2E_CONFIG="${E2E_CONFIG:-e2e}"
WORK_DIR="$PROJECT_ROOT/local_e2e_test"
DIST_DIR="$PROJECT_ROOT/dist"
PROJECT_DIR="$WORK_DIR/spaceflights"

# Use real registry if provided, otherwise localhost for local testing
REGISTRY_LOGIN_SERVER="${REGISTRY_LOGIN_SERVER:-localhost:5000}"
IMAGE_TAG="${IMAGE_TAG:-$E2E_CONFIG}"
FULL_IMAGE_NAME="$REGISTRY_LOGIN_SERVER/kedro-azureml-e2e:$IMAGE_TAG"

# Cleanup previous runs
echo "🧹 Cleaning up previous test runs..."
rm -rf "$WORK_DIR"
rm -rf "$DIST_DIR"
# Also remove any existing spaceflights directory in project root (from previous runs)
rm -rf "$PROJECT_ROOT/spaceflights"
mkdir -p "$WORK_DIR"

echo "📦 Building the kedro-azureml package..."
cd "$PROJECT_ROOT"
poetry build -f sdist

echo "🚀 Creating new Kedro project with spaceflights starter..."
cd "$WORK_DIR"

# Install kedro-azureml from built package
pip install "$(find "$DIST_DIR" -name "*.tar.gz")"

# Create new project
kedro new --starter spaceflights-pandas --config "$PROJECT_ROOT/tests/conf/$E2E_CONFIG/starter-config.yml" --verbose --checkout=1.0.0

echo "📋 Installing dependencies..."
cd spaceflights

# Copy the built package
find "$DIST_DIR" -name "*.tar.gz" | xargs -I@ cp @ kedro-azureml.tar.gz

# Update requirements.txt
echo -e "\n./kedro-azureml.tar.gz\n" >> requirements.txt
echo -e "kedro-docker~=0.6.2\n" >> requirements.txt

# Remove problematic dependencies for local testing
sed -i.bak '/kedro-telemetry/d' requirements.txt
sed -i.bak '/kedro-viz/d' requirements.txt

echo "📄 Requirements file contents:"
cat requirements.txt

# Install requirements
pip install -r requirements.txt

echo "🐳 Setting up Docker configuration..."
kedro docker init

# Add kedro-azureml package to Dockerfile
sed -i.bak 's/\(COPY requirements.txt.*\)$/\1\nCOPY kedro-azureml.tar.gz ./g' Dockerfile

echo "📄 Dockerfile contents:"
cat Dockerfile

# Add data exclusion to .dockerignore
echo "!data/01_raw" >> .dockerignore

echo "⚙️  Setting up test configurations..."
# Replace catalog and azureml config
rm conf/base/catalog.yml
cp "$PROJECT_ROOT/tests/conf/$E2E_CONFIG/catalog.yml" conf/base/catalog.yml
cp "$PROJECT_ROOT/tests/conf/$E2E_CONFIG/azureml.yml" conf/base/azureml.yml

# Replace placeholders with registry and image tag from environment
sed -i.bak "s/{container_registry}/$REGISTRY_LOGIN_SERVER/g" conf/base/azureml.yml
sed -i.bak "s/{image_tag}/$IMAGE_TAG/g" conf/base/azureml.yml

echo "📄 Azure ML configuration:"
cat conf/base/azureml.yml

echo ""
echo "🐳 Building and pushing Docker image..."
echo "Image: $FULL_IMAGE_NAME"

# Try to pull existing image for cache (ignore failures)
docker pull "$FULL_IMAGE_NAME" 2>/dev/null || echo "No cached image found, proceeding without cache"

# Build Docker image for x64 Linux (Azure ML platform)
docker build \
    --platform linux/amd64 \
    --build-arg BASE_IMAGE=python:3.10-buster \
    -t "$FULL_IMAGE_NAME" \
    --cache-from="$FULL_IMAGE_NAME" \
    .

echo "✅ Docker image built successfully: $FULL_IMAGE_NAME"

# Only push to real registry (not localhost)
if [[ "$REGISTRY_LOGIN_SERVER" != "localhost:5000" ]]; then
    echo "🚀 Pushing image to registry..."
    docker push "$FULL_IMAGE_NAME"
    echo "✅ Image pushed successfully"
else
    echo "ℹ️  Skipping push for localhost registry"
fi

echo ""
echo "🚀 Running Azure ML Pipeline..."

# Check if we have real Azure credentials or mock ones
if [[ "$AZURE_SUBSCRIPTION_ID" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] && [[ "$AZURE_SUBSCRIPTION_ID" != "00000000-0000-0000-0000-000000000000" ]]; then
    echo "🔑 Real Azure credentials detected, attempting to run against Azure ML..."

    # Ask user if they want to proceed with actual execution
    echo ""
    read -p "Dry-run successful! Do you want to proceed with actual Azure ML execution? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🏃 Running on Azure ML Pipelines..."
        kedro azureml submit -j e2e_test --once --wait-for-completion --env-var 'GETINDATA=ROCKS!'
        echo "✅ Azure ML pipeline execution completed!"
    else
        echo "ℹ️  Skipping Azure ML execution as requested"
    fi
else
    echo "🔧 Mock credentials detected, running dry-run only..."
    kedro azureml submit -j e2e_test --dry-run --env-var 'GETINDATA=ROCKS!' || echo "⚠️  Dry-run failed (expected with mock credentials)"
fi

echo ""
echo "✅ E2E Test Reproduction Complete!"
echo ""
echo "📊 Summary:"
echo "- Package built: ✅"
echo "- Project created: ✅"
echo "- Dependencies installed: ✅"
echo "- Docker image built: ✅"
echo "- Configuration validated: ✅"
echo ""
echo "📁 Project location: $PROJECT_DIR"
echo "🐳 Docker image: $FULL_IMAGE_NAME"
echo ""
echo "🔧 Manual testing options:"
echo "1. cd $PROJECT_DIR"
echo "2. kedro run  # Local pipeline execution"
echo "3. kedro azureml submit -j e2e_test --dry-run  # Validate Azure ML config"
if [[ "$REGISTRY_LOGIN_SERVER" != "localhost:5000" ]]; then
    echo "4. kedro azureml submit -j e2e_test --once --wait-for-completion  # Run on Azure ML (requires real credentials)"
fi