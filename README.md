> ⚠️ WARNING  
> OrbitLab is under ***HEAVY*** active development and is considered **pre-alpha** software. Expect breaking changes, incomplete features, and sharp edges.  
> ***Do not run in production. Use at your own risk.***

[Roadmap](/docs/roadmap.md)

# OrbitLab

OrbitLab is an **infrastructure orchestration layer and control plane for Proxmox VE**. It utilizes Proxmox primitives for creating and managing a self-hosted lab environment in a "cloud-like" way in efforts to ensure a fault-tolerant and scalable architecture. OrbitLab is **not** a replacement for Proxmox. In fact, you wouldn't be able to use OrbitLab without Proxmox, as it requires to be installed inside the Proxmox node.

This screenshots below provide an overview of OrbitLab and some of the services via the UI. More documentation will come, but this has been a long haul project I've worked on off-and-on for over a year and some change now. A lot of the original architecture and methodology has changed, but the ethos remain the same: make home-labbing more fun, less stressful, more resilient, and self-healing (as best as I can).



### Tech stack

OrbitLab installs Redis and Redis Sentinel for configuration and state management. It also uses Reflex as the primary UI, which is essentially Python-wrapped React compiled to static HTML. The `*.deb` installed UI is pretty snappy, but the development leaves a lot to be desired. So, I'm debating about making the swich to NiceGUI, which uses Vue/Quasar but the dev experience is snappier and I can use more Python primitives and get out of a secondary Var management system. The event-driven mechanisms are Redis streams. The eventual goal is to use Redis Sentinel for full Proxmox cluster support.


## System Initialization

The initialization screen guides users through the initial setup process for OrbitLab.

![Initialize](/docs/screenshots/initialize.JPG)



## Dashboard

***HEAVY WIP***

The main dashboard provides an overview of OrbitLab's infrastructure health.

![Dashboard](/docs/screenshots/dashboard.JPG)



## Sectors

Sectors are isolated network segments connected by OrbitLab's Backplane, allowing for CIDR overlap between Sectors without conflict (as the Sector Gateway handles SNAT/DNAT).
Each sector can also be configured with Conduit (Traefik) or WardLink (WireGuard) appliances. The Conduit appliance provides ingress and load balancing (and TLS), and the 
WardLink appliance provides a WireGuard connection (in a similar fashion to Conduit) but provides a direct link to the Sector for SSH access. 

The Sector Gateway uses `frr` and `nftables` to provide Sector routing and SNAT/DNAT with the Backplane. It uses CoreDNS as the primary DNS mechanism and is integrated with the primary Backplane DNS. Technically, all DNS records are stored in Redis. This is to allow Sector-isolated DNS configurations that can all be served from the Backplane. It also uses Dnsmasq as DHCP. 

> NOTE: SSH key integration is still not fully implemented, but it's on the Roadmap. The main chunks are there, they just need to be wired up correctly. 

![Sectors](/docs/screenshots/sectors.JPG)


## Compute Instances

Compute Instances are configured, allocated resources, and then attached to a given Sector. The Sector assigns IPv4 addresses via DHCP and tracks any integrations with other services, like Conduit Pools. All managed infrastructure and user-launched compute is assigned determinstic MAC addresses, which should help keep addressing stable, but it's not a guarantee.

OrbitLab treats LXC and QEMU very similarly in a configuration sense, but is aware of the differences when it comes to management. I've also been toying
with the idea of using customizable T-shirt sizes for faster and easier compute allocation and management.

![Compute Instances](/docs/screenshots/compute.JPG)



## LXC/QEMU Management and Customization

Here you can download Proxmox's managed LXCs, or OrbitLab's managed QCOW2 images for your own use, and even customize them with workflows. 

![LXC Appliances](/docs/screenshots/custon_lxc.JPG)

![VM Appliances](/docs/screenshots/custon_qemu.JPG)



## Secrets Management

Since OrbitLab manages certain infrastructure for you, and most of them require some sort of secret or credential, OrbitLab has built-in secrets management using `AESGCM` 
encryption. It supports creation and even injection into LXC/QEMU workflow scripts. 

> NOTE: Documentation still needed on workflow scripts, but it's possible using `@OL_SECRET[/my/secret/name]@` where `/my/secret/name` is the name given to your secret in OrbitLab. If the secret is a JSON string, you can use `@OL_SECRET[/my/secret/name][/client_id]@` to access the `client_id` key.
 
![Secrets](/docs/screenshots/secrets.JPG)

The Public Key Infrastructure (PKI) management interface provides certificate lifecycle management, including certificate authority operations, certificate issuance, and renewal workflows.


## Proxmox Integration

There is not much here other than displaying the nodes OrbitLab is partnered with (read: *installed on*). Eventually, when cluster support is built, this will be updated to allow for HA group management and maintenance (enable/disable maintenance mode and updating Proxmox).

![Proxmox](/docs/screenshots/proxmox_nodes.JPG)



## DataCores

DataCores are managed Patroni/PostgreSQL clusters. You can create them with a minimum of 1 replica and the endpooints are static by using VIPs with keepalived that is integrated with Patroni's control and state. This allows for DB failover and even replica termination and recreation. 

![Secrets](/docs/screenshots/datacores.JPG)


## DockFS

DockFS is a network fileshare (NFS) active/passive cluster. It creates a simple VM (due to NFS kernel requirements) and attaches a data disk (SCSI1) that is your specified storage size. Upon active node failure, it is stopped, the data disk migrated to the passive node, passive node is flipped to active, and the old node it terminated and replaced. 

![Secrets](/docs/screenshots/dock_fs.JPG)


## Conduit

Conduit is a managed Traefik LXC that bridges Proxmox's `vmbr0` with your specified Sector. Assuming `vmbr0` is on your same LAN network as your home and other machines, they should be able to access any service inside your Sector that you configure. Conduit Pools are Traefik Services, and Conduit Endpoints are Traefik Routers. You can also configure a Domain Provider (currently only Cloudflare) which will manage wildcard certificates for a given domain you own. 

![Conduit](/docs/screenshots/conduit.JPG)

![Domain Providers](/docs/screenshots/domain_providers.JPG)
