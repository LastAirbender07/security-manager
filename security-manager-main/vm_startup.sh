#!/bin/bash
set -e

# 1. Update and Install Dependencies
echo "Updating system..."
apt-get update
apt-get install -y ca-certificates curl gnupg lsb-release

# 2. Install Docker
echo "Installing Docker..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=\"$(dpkg --print-architecture)\" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  \"$(. /etc/os-release && echo \"$VERSION_CODENAME\")\" stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3. Configure Docker
systemctl start docker
systemctl enable docker

# 4. Allow all users to run docker (convenience for this lab)
# In production, manage users carefully.
chmod 666 /var/run/docker.sock

echo "VM Startup Complete. Docker is ready."
