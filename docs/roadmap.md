# Phase 1

- [x] Backplane 
  - [x] EVPN Controller
  - [x] EVPN Zone
  - [x] VNet (user-defined CIDR or 10.200.0.0/16)
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

# Phase 2

- [ ] Logging
  - [ ] Clients
  - [ ] Application
  - [ ] Viewable in UI
- [ ] Custom LXC Appliances
  - [x] General Configuration
  - [x] Network Configuration
  - [x] Workflow Steps
    - [x] Uploaded Files
    - [x] Custom Bash Scripts
  - [ ] Edit Existing Custom Appliances  
  - [ ] Launch Custom Appliance in Sector
- [ ] Deployable
  - [ ] DEB release for installation
  - [ ] Serves static HTML
  - [ ] Runs backend (minimize deps as much as possible)
  - [ ] Self updating mechanism (user-triggered)

# Phase 3

- [ ] Autoscaling Pools
  - [ ] Backend Watcher
  - [ ] Health Checks
- [ ] DataCores (RDS-like DB service)
  - [ ] ETCD (Opt-In): 3-node LXC cluster
    - [ ] Create Cluster and validate Health
      - Add necessary Backplane IPs to Sector GWs (nftables)
    - [ ] Monitor Cluster Health: Replace each node as needed:
      - Remove Member (from healthy member)
      - Rebuild LXC (control plane)
      - Add Member (from healthy member)
      - Boot New Member with required parameters
  - [ ] Patroni/PostgreSQL
    - [ ] Update DNS A record on role change
    - [ ] Health checks for monitoring
- [ ] HAproxy Ingress: vmbr0 and sector to provide external access (Home LAN)
  - [ ] HTTP
  - [ ] HTTPS
  - [ ] TCP
  - [ ] UDP 


# Phase 4

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
