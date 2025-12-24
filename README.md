> ⚠️ WARNING  
> OrbitLab is under ***HEAVY*** active development and is considered **pre-alpha** software.  
> Expect breaking changes, incomplete features, and sharp edges.  
> ***Do not run in production. Use at your own risk.***

[Screenshots](/docs/orbitlab_screenshots.md)

# OrbitLab

OrbitLab is a **manifest-driven infrastructure orchestration layer for Proxmox VE**.  
Its goal is to transform a Proxmox cluster into a **deterministic, cloud-inspired platform** for building fault-tolerant, scalable workloads *without abandoning Proxmox’s native primitives*.

OrbitLab is **not** a replacement for Proxmox.  
It is a **control plane that formalizes cluster state**, networking, and lifecycle automation using declarative manifests stored directly in the Proxmox Cluster Filesystem (PMXCFS).

This allows you to run OrbitLab on a single Proxmox node, a massive enterprise-grade cluster, or anywhere in-between. It's built for home-labbers, but designed to scale as you do.

## What OrbitLab Is (and Is Not)

I originally started building OrbitLab to help with my home lab in terms of DB resiliency (initially). I wanted to create an RDS-type service where I could spin up PostgreSQL/Patroni database clusters (usually 2 for failover) that was smart enough to
check db status and reboot/replace if necessary. And then have automatic local DNS resolution within the same network so I can create one with a couple clicks and then use it for self-hosted services that require a DB. It branched out into wanting 
auto-scaling pools of machines for other workloads (e.g. workers, Docker Swarm nodes, etc.) and being able to integrate local DNS and load balancing (HAproxy) with it as well. 

**OrbitLab is:**
- A **cluster-aware orchestration system** for Proxmox
- Opinionated about networking, isolation, and determinism
- Designed for **HA pools of VMs/LXCs**, not pets (although you can have your pets in OrbitLab).
- Built to support higher-level services (databases, gateways, PKI, secrets)

**OrbitLab is not:**
- A generic “cloud abstraction layer”
- A Kubernetes replacement
- A dynamic routing playground
- A multi-cloud control plane
- A UI-only management tool

If you want **predictable behavior, isolated networks and failure domains, and explicit opinionated control**, OrbitLab is designed for you.


## Core Design Principles

### Declarative Cluster State

Everything OrbitLab manages is defined as a **typed manifest**:
- Cluster
- Nodes
- Sectors (OrbitLab's version of a VPC)
- LXCs
- Appliances
- Secrets, certificates, SSH keys
- Global OrbitLab settings

Manifests are:
- Validated via Pydantic schemas
- Stored in PMXCFS
- Resolved via explicit references
- Designed to be human-readable and auditable

This makes OrbitLab inherently GitOps-friendly and cluster-aware without inventing a parallel state store.

### Proxmox-Native First

OrbitLab builds *on top of* Proxmox features instead of reimplementing them:
- PMXCFS for shared state
- Proxmox SDN (EVPN/VXLAN)
- LXC appliances and templates
- HA groups
- Native storage backends
- `pvesh` and API access

If Proxmox can already do something reliably, OrbitLab can orchestrate it. It doesn’t replace it.

## Architecture Overview

### Control Plane

The OrbitLab control plane is responsible for:
- Discovering cluster state
- Validating manifests
- Reconciling desired vs actual state
- Coordinating actions across nodes

There is no always-on “brain” process required for correctness.  
State lives in manifests, not memory.

### Manifest Engine

Manifests are:
- Schema-driven
- Strongly typed
- Explicitly linked via references
- Serialized back into YAML after validation

This enables:
- Safe refactoring
- Dependency resolution
- Partial reconciliation
- Predictable upgrades

See the manifest schema system for examples.

### Networking Model

All networking configurations managed by OrbitLab have an integrated IPAM for IPv4 allocation and tracking.

**Backplane**
- Cluster-wide EVPN-backed network
- Fixed CIDR set at initialization
- Used for inter-node services and gateways
- Cannot be reconfigured after creation

**Sectors**
- Isolated VXLAN-backed L3 environments
- Overlapping CIDRs allowed
- Each Sector has:
  - A Gateway (FRR + nftables)
  - Internal DNS (***WIP***)
- All ingress/egress is explicit

This mirrors cloud-style VPC isolation without requiring VRFs everywhere.

**Future services**

None of these currently exist today, but they are on the roadmap for completion.

- Sector DNS (CoreDNS): Provides in-Sector hostname/FQDN resolution using `*.orbitlab.internal`.
- Home LAN DNS (CoreDNS): Allow for local home LAN resolution of OrbitLab endpoints for service access (requires configuring your home router to forward specific zones to OrbitLab's resolver)
- Database-as-a-Service (ETCD/Patroni/PostgreSQL): A few simple clicks and selections to create resilient databases.
- Load Balancing (HAProxy): Load Balance across multiple compute instances in a pool using a VIP assigned by the integrated IPAM.
- Auto-Scaling: Using VM/LXC templates, create pools of compute with configurable health checks to ensure your applications stay highly available.
- Public Ingress (Cloudflared/Tailscale/Pangolin): User-configurable ingress integrations to provide public access to services within your private Sector.

A key benefit of note here is that you can create multiple Sectors for various services/applications and keep them isolated networking-wise.
You could use Cloudflare tunnels for HTTP(S) applications in one sector, and Tailscale/Pangolin in another for Jellyfin/Plex streaming with no risk of cross-contamination. Could you
do this directly in Proxmox? Sure. But OrbitLab helps to make it faster and easier to manage instead of hand-tracking IPs (or integrating another service like Netbox) and compute resources.

## Key Capabilities (Current & Near-Term)

### Infrastructure
- Proxmox cluster discovery
- Node lifecycle awareness
- Storage selection and safety checks
- Appliance-backed LXC provisioning

### Networking
- Automated EVPN/VXLAN setup
- Backplane initialization
- Sector creation and teardown
- Deterministic gateway behavior
- In-Sector DNS (***WIP***)

### Security Foundations
- Encrypted secret vault (AES-GCM)
- Versioned secrets with rollback
- Internal PKI:
  - Root CAs
  - Intermediate CAs
  - Leaf certificates
- SSH key lifecycle management

### Operational Safety
- Strong validation before mutation
- Explicit references instead of implicit discovery
- Conservative defaults
- No hidden automation

## Intended Use Cases

OrbitLab is particularly well-suited for:

- **Home labs that want cloud-like structure**
- **Small clusters running HA workloads**
- **Edge deployments with limited resources**
- **Database-heavy environments**
- **Infrastructure engineers who value clarity over magic**

## Project Status

OrbitLab is:
- Actively evolving
- Opinionated by design
- Built for correctness first
- Not yet feature-complete

Expect:
- Schema changes
- Networking refinements
- Appliance evolution
- Better reconciliation logic

## Philosophy

OrbitLab treats infrastructure as:
> *A system of explicit contracts, not emergent behavior.*

If that resonates with you, you’re the target audience.
