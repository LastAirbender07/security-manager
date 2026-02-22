terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.8.0"
    }
  }
}

provider "google" {
  project = "ai-connect-sap26blr-307"
  region  = "us-central1"
  zone    = "us-central1-c"
}

# -------------------------------
# VPC Network
# -------------------------------
resource "google_compute_network" "vpc_network" {
  name                    = "terraform-hackathon-network"
  auto_create_subnetworks = true
}

# -------------------------------
# Firewall: Frontend + Backend
# -------------------------------
resource "google_compute_firewall" "allow_web" {
  name    = "allow-frontend-backend"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["5173", "8000"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["hackathon-vm"]
}

# -------------------------------
# Firewall: SSH Access
# -------------------------------
resource "google_compute_firewall" "allow_ssh" {
  name    = "allow-ssh"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["hackathon-vm"]
}


# -------------------------------
# Compute Engine VM
# -------------------------------
resource "google_compute_instance" "vm_instance" {
  name         = "terraform-hackathon-vm"
  machine_type = "e2-standard-4"
  zone         = "us-central1-c"
  tags         = ["hackathon-vm"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 50
    }
  }

  network_interface {
    network = google_compute_network.vpc_network.name
    access_config {}
  }

  metadata = {
    startup-script = <<-EOT
      #!/bin/bash
      set -euxo pipefail

      LOG=/var/log/startup-script.log
      exec > >(tee -a "$LOG") 2>&1

      echo "===== GCE startup script started ====="
      date

      echo "===== Installing base packages ====="
      apt-get update
      apt-get install -y curl git ca-certificates

      echo "===== Installing Docker ====="
      curl -fsSL https://get.docker.com | sh
      systemctl enable docker
      systemctl start docker

      echo "===== Waiting for Docker daemon ====="
      until docker info >/dev/null 2>&1; do
        sleep 2
      done

      echo "===== Installing Docker Compose ====="
      curl -L https://github.com/docker/compose/releases/download/v2.29.2/docker-compose-linux-x86_64 \
        -o /usr/local/bin/docker-compose
      chmod +x /usr/local/bin/docker-compose

      docker --version
      docker-compose version

      echo "===== Cloning application repository ====="
      mkdir -p /opt
      cd /opt
      rm -rf security-manager-AI-Connect
      git clone https://github.com/LastAirbender07/security-manager-AI-Connect.git

      echo "===== Starting application stack ====="
      cd /opt/security-manager-AI-Connect/security-manager-main
      chmod +x start_all.sh
      ./start_all.sh

      echo "===== Startup script completed successfully ====="
      date
    EOT
  }
}


# ------------------------------- # Outputs
# -------------------------------
output "vm_public_ip" {
  description = "Public IP of the Hackathon VM"
  value       = google_compute_instance.vm_instance.network_interface[0].access_config[0].nat_ip
}
