# OrbitLab

OrbitLab is an AWS Console-style service suite for managing Proxmox infrastructure.

Key goals
- Provide a small, modular control plane for lab infrastructure and appliances that sits thinly on top of Proxmox.
- Offer manifest schemas and clients to validate and apply declarative configs synchronoized via PMXCFS.
- Expose a lightweight web UI and APIs for inspection, management, and automation not already provided in Proxmox.


## Development Notes

1. Only about to create 1 EVPN controller per cluster.
    - To enable VPC-like networking, the main EVPN Zone will be pure infrastructure.
    - 


(192.168.87.236)
192.168.2.37/24
192.168.86.37/23

192.168.2.40/24
192.168.86.40/22

192.168.86.1
https://storage.googleapis.com/nvidia-drivers-us-public/GRID/vGPU16.4/NVIDIA-Linux-x86_64-535.161.07-grid.run