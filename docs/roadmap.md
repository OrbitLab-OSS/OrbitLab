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
- [x] Launch Base Image in Sector

# Phase 2

- [x] VM Images
  - [x] Create pre-made cloud images containing qemu-agent
    - [x] Debian 13
    - ?
- [x] Custom Appliances and Images
  - [x] General Configuration
  - [x] Network Configuration
  - [x] Workflow Steps
    - [x] Uploaded Files
    - [x] Custom Bash Scripts
  - [x] Edit Existing Custom Appliances and Images  
- [ ] DockFS
  - [ ] Create custom NFS image
  - [ ] 
- [ ] Deployable
  - [ ] DEB release for installation
  - [ ] Serves static HTML
  - [ ] Runs backend (minimize deps as much as possible)
  - [ ] Self updating mechanism (user-triggered)


# Phase 3
`etcd --name $NODE_NAME --discovery-srv orbitlab.internal --initial-advertise-peer-urls http://$NODE_IP:2380 --initial-cluster-token etcd-cluster-3 --initial-cluster-state new  --advertise-client-urls http://$NODE_IP:2379 --listen-client-urls http://$NODE_IP:2379 --listen-peer-urls http://$NODE_IP:2380 --heartbeat-interval 200 --election-timeout 2000`
- [ ] ETCD (Opt-In): 3-node LXC cluster
  1. Pull down pre-configured appliance
  2. Generate client/server/peer certs
  3. Create ETCD pool and launch LXCs
  4. Push certs to LXCs (add to trust store)
  5. Bootstrap ETCD cluster
  - [ ] Create Cluster and validate Health
    - Add necessary Backplane IPs to Sector GWs (nftables)
  - [ ] Monitor Cluster Health: Replace each node as needed:
    - Remove Member (from healthy member)
    - Rebuild LXC (control plane)
    - Add Member (from healthy member)
    - Boot New Member with required parameters
- [ ] Autoscaling Pools
  - [ ] Backend Watcher
  - [ ] Health Checks
- [ ] Logging
  - [ ] Clients
  - [ ] Application
  - [ ] Viewable in UI
- [ ] DataCores (RDS-like DB service)
  - [ ] Patroni/PostgreSQL
    - [ ] Update DNS A record on role change
    - [ ] Health checks for monitoring
- [ ] HAproxy Ingress: vmbr0 and sector to provide external access (Home LAN)
  - [ ] HTTP
  - [ ] HTTPS
  - [ ] TCP
  - [ ] UDP 


# Phase 4
- [ ] Support Root CAs in workflows
  - [ ] Generate `orbitlab.internal` Root/Intermediate CAs on initialization
    - [ ] Track cert expiration
  - [ ] LXCs
  - [ ] VMs
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
