# Phase 1

- [x] Backplane 
  - [x] EVPN Controller
  - [x] EVPN Zone
  - [x] VNet (user-defined CIDR or 10.200.0.0/16)
  - [ ] DNS (CoreDNS)
  - [x] IPAM (Track IP registration)
- [ ] Storage (Linstor)
  - [ ] Install
  - [ ] Configure

# Phase 2

- [x] Sectors (VNets)
  - [x] VXLAN
  - [x] VNet
  - [x] Router (FRR/NFTables)
    - [x] Custom LXC Appliance
    - [x] FRR
    - [x] NFTables
  - [ ] DNS (CoreDNS)
  - [x] IPAM (Track IP registration)

# Phase 3

- Custom LXC Appliances
- HAproxy Ingress
  - User vmbr0 and VNet to provide external access (Home LAN)
- RDS (Opt-In)
  - ETCD Backend Service
  - Patroni/PostgreSQL


# Phase 4

- Public Access
  - Cloudflared
  - ?
- Reverse-Proxy Auth (?)
