# Phase 1

- [x] Backplane 
  - [x] EVPN Controller
  - [x] EVPN Zone
  - [x] VNet (user-defined CIDR or 100.96.0.0/16)
  - [x] IPAM (Track IP registration)
  - [x] DNS (CoreDNS)
- [x] Sectors (VNets)
  - [x] VXLAN
  - [x] VNet
  - [x] Router (FRR/NFTables)
    - [x] Custom LXC Appliance
    - [x] FRR
    - [x] NFTables
  - [x] IPAM (Track IP registration)
  - [x] DNS
    - [x] Create Zone
    - [x] Add/Remove A Records
- [x] Launch Base LXC in Sector
- [x] Launch Base Image in Sector

# Phase 2

- [x] VM Images
  - [x] Create pre-made cloud images containing qemu-agent
    - [x] Debian 13
    - [x] DockFS
- [x] Custom Appliances and Images
  - [x] General Configuration
  - [x] Network Configuration
  - [x] Workflow Steps
    - [x] Uploaded Files
    - [x] Custom Bash Scripts
  - [x] Edit Existing Custom Appliances and Images 
- [x] Orbital Relay (enable HTTP API calls from Backplane or Sectors to Control Plane)
- [x] DockFS
  - [x] Create custom NFS image
- [x] ETCD (Opt-In): 3-node LXC cluster
  - [x] Create Cluster and validate Health
  - [x] Monitor Cluster Health: Replace each node as needed
- [x] DataCores (RDS-like DB service)
  - [x] Patroni/PostgreSQL

# Phase 3

- [ ] Check/Update infrastructure appliances
- [ ] Autoscaling Pools
  - [ ] Templates
  - [ ] Health Checks
- [ ] Logging
  - [ ] Clients
  - [X] Application
  - [X] Viewable in UI
- [ ] Deployable
  - [x] DEB release for installation
  - [x] Serves static HTML
  - [x] Runs backend (minimize deps as much as possible)
  - [ ] Self updating mechanism (user-triggered)

# Phase 4

- [ ] EdgeGate(HAproxy Ingress)
  - [ ] Private (Only accessible from within the Sector) (attached to Sector)
  - [ ] Internal (Only accessible from within OrbitLab) (attached to Sector and Backplane)
  - [ ] External (Accessible from LAN) (attached to Proxmox vmbr0 and Sector)
- [ ] Implement HTTPS everywhere
  - [ ] Generate `orbitlab.internal` Root/Intermediate CAs on initialization
    - [ ] Track cert expiration
  - [ ] DockFS
  - [ ] DataCore
  - [ ] ETCD
  - [ ] Orbital Relay
- [ ] Sector Public Access
  - [ ] Cloudflared
  - [ ] Tailscale
  - [ ] Pangolin
- [ ] Full Cluster Support
  - [ ] Replicate application across nodes
    - [ ] Create processes in all nodes for HA
    - [ ] Detect new version and Update
  - [ ] Shared Storage (Linstor)
    - [ ] Install
    - [ ] Configure
- [ ] Reverse-Proxy Auth (? - Not to sure about this)
  - [ ] Authelia/Authentik
