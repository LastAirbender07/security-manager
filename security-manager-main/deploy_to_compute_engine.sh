#!/bin/bash
set -e

# Configuration
PROJECT_ID="ai-connect-sap26blr-307"
ZONE="us-central1-a"
INSTANCE_NAME="security-management-vm"
MACHINE_TYPE="e2-medium"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"

echo "============================================="
echo "Deploying to GCP Compute Engine"
echo "Project: $PROJECT_ID"
echo "Zone: $ZONE"
echo "Instance: $INSTANCE_NAME"
echo "============================================="

# 1. Create the VM Instance
echo "Checking if instance $INSTANCE_NAME exists..."
if gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --project=$PROJECT_ID &>/dev/null; then
    echo "Instance $INSTANCE_NAME already exists. Skipping creation."
else
    echo "Instance not found. Creating instance $INSTANCE_NAME..."
    gcloud compute instances create $INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$ZONE \
        --machine-type=$MACHINE_TYPE \
        --image-family=$IMAGE_PROJECT \
        --image-project=$IMAGE_PROJECT \
        --tags=http-server,https-server \
        --scopes=cloud-platform \
        --metadata-from-file=startup-script=vm_startup.sh

    echo "Instance created. Waiting for startup script to finish (approx 2-3 mins)..."
    # We sleep a bit to let the VM boot and start the script
    sleep 30
fi

# 2. Configure Firewall
echo "Configuring firewall rules..."
if ! gcloud compute firewall-rules describe allow-app-ports --project=$PROJECT_ID &>/dev/null; then
  gcloud compute firewall-rules create allow-app-ports \
      --project=$PROJECT_ID \
      --allow tcp:8000,tcp:5173 \
      --target-tags=http-server
  echo "Firewall rules created (8000, 5173)."
else
  echo "Firewall rule 'allow-app-ports' already exists."
fi

# 3. Copy Application Code
echo "Copying application code to the VM..."
# Exclude huge folders like node_modules or venv/env locally to speed up transfer
# We'll use rsync exclude file or manual exclusions
# Clean up local temp file just in case
rm -f .gcpignore 2>/dev/null
echo "node_modules" > .gcpignore
echo "__pycache__" >> .gcpignore
echo ".git" >> .gcpignore
echo "venv" >> .gcpignore
echo "env" >> .gcpignore

# Compress project for faster transfer
echo "Compressing project files..."
tar -czf project_bundle.tar.gz \
    --exclude='node_modules' \
    --exclude='env' \
    --exclude='venv' \
    --exclude='.git' \
    --exclude='__pycache__' \
    .

echo "Uploading bundle to VM..."
gcloud compute scp project_bundle.tar.gz $INSTANCE_NAME:~ --zone=$ZONE --project=$PROJECT_ID

# 4. Deploy and Run
echo "Executing deployment on VM..."
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --project=$PROJECT_ID --command '
    # Install unzip and tools just in case
    sudo apt-get install -y tar

    # Create app directory
    mkdir -p ~/app
    tar -xzf project_bundle.tar.gz -C ~/app
    
    cd ~/app
    
    # Ensure Docker is ready (in case startup script is still running)
    echo "Waiting for Docker to be ready..."
    until sudo docker info > /dev/null 2>&1; do sleep 5; echo "."; done
    
    # Start the stack
    echo "Starting Docker Compose stack..."
    # We need to use "sudo" for docker commands unless we added the user to the docker group and relogged
    sudo docker compose down --remove-orphans || true
    sudo docker compose up -d --build
    
    echo "Deployment commanded successfully."
'

# 5. Get External IP
EXTERNAL_IP=$(gcloud compute instances describe $INSTANCE_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo "============================================="
echo "Deployment Complete!"
echo "App URL (Frontend): http://$EXTERNAL_IP:5173"
echo "API URL (Backend):  http://$EXTERNAL_IP:8000/docs"
echo "============================================="
