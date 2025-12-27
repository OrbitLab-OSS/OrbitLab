# Phase 1

- [x] Backplane 
  - [x] EVPN Controller
  - [x] EVPN Zone
  - [x] VNet (user-defined CIDR or 10.200.0.0/16)
  - [x] IPAM (Track IP registration)
- [x] Sectors (VNets)
  - [x] VXLAN
  - [x] VNet
  - [x] Router (FRR/NFTables)
    - [x] Custom LXC Appliance
    - [x] FRR
    - [x] NFTables
  - [x] IPAM (Track IP registration)

# Phase 2

- [ ] Logging
  - [ ] Clients
  - [ ] Application
- [ ] Custom LXC Appliances
  - [x] General Configuration
  - [x] Network Configuration
  - [x] Workflow Steps
    - [x] Uploaded Files
    - [x] Custom Bash Scripts
  - [ ] Edit Existing Custom Appliances
- [ ] Sector DNS (CoreDNS)
  - [ ] Add/Remove A Records

# Phase 3

- [ ] HAproxy Ingress: vmbr0 and sector to provide external access (Home LAN)
  - [ ] HTTP
  - [ ] HTTPS
  - [ ] TCP
  - [ ] UDP 
- [ ] DataCores (RDS-like DB service)
  - [ ] ETCD: Key/Value mgmt for Patroni
  - [ ] Patroni/PostgreSQL
    - [ ] Update DNS A record on role change
    - [ ] Health checks for monitoring
- [ ] Sector Public Access
  - [ ] Cloudflared
  - [ ] Tailscale
  - [ ] Pangolin

# Phase 4

- [ ] Full Cluster Support
  - [ ] Replicate application across nodes
    - [ ] Create processes in all nodes for HA
    - [ ] Detect new version and Update
  - [ ] Shared Storage (Linstor)
    - [ ] Install
    - [ ] Configure
- [ ] Reverse-Proxy Auth (? - Not to sure about this)
  - [ ] Authelia/Authentik
