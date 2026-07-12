# Roadmap
This is the general roadmap of features and implementations for OrbitLab. This is all subject to change based upon 
numerous factors. Suggestions and requests are accepted but may not be implemented, or may be paved over with 
another compatible mechanism.

# Phase 1

- [x] Backplane 
  - [x] EVPN Controller
  - [x] EVPN Zone
  - [x] VNet (user-defined CIDR or 100.96.0.0/16)
  - [x] DNS (CoreDNS)

- [x] Sectors (VNets)
  - [x] VXLAN
  - [x] VNet
  - [x] Router (FRR/NFTables)
    - [x] Custom LXC Appliance
    - [x] FRR
    - [x] NFTables
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

- [x] Check/Update infrastructure appliances

- [x] Logging
  - [X] Application
  - [X] Viewable in UI

- [x] Deployable (not yet integrated with GitHub actions though)
  - [x] DEB release for installation
  - [x] Serves static HTML
  - [x] Runs backend (minimize deps as much as possible)

- [x] Conduit (Traefik Ingress attached to Proxmox vmbr0 and Sector)
  - [x] Pools (Traefik Services - a collection of instances to load balance)
  - [x] Endpoints (Traefik Routers - HTTP/HTTPS)
    - [x] DNS Provider Support (Cloudflare)

- [x] WardLink (WireGuard appliance attached to Proxmox vmbr0 and Sector)
  - [x] Add clients with generated configs

- [x] Inject secrets into Custom Appliance/Image workflow scripts

# Phase 4

- [ ] Built-in Markdown documentation 

- [ ] Self updating mechanism (user-triggered)

- [ ] Additional logging information (?)

- [ ] Full Cluster Support
  - [ ] Replicate application across nodes
    - [ ] Create processes in all nodes for HA
    - [ ] Detect new version and Update
  - [ ] Shared Storage (Linstor?)
    - [ ] Install
    - [ ] Configure

- [ ] Conduit Features
  - [ ] Additional DNS Providers (?)
  - [ ] Authelia/Authentik integrations (?)

- [ ] Autoscaling Pools
  - [ ] Templates (LXC/QEMU)
  - [ ] Health Checks (Same as Conduit?)

- [ ] Implement HTTPS everywhere
  - [ ] Generate `orbitlab.internal` Root/Intermediate CAs on initialization
    - [ ] Track cert expiration
  - [ ] DataCore
  - [ ] ETCD
  - [ ] Orbital Relay
