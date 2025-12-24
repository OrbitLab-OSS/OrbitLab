# OrbitLab Networks

## Backplane

Part of the OrbitLab initialization process is to create a Backplane network that spans all known Proxmox nodes to provide a resilient and dynamic network to facilitate network connectivity for all VMs/LXCs in all Sectors regardless of the Proxmox node they're attached to. 

> NOTE: OrbitLab's Backplane network is `10.200.0.0/16`, but can be assigned differently upon initialization. However, once initialized, the Backplane ***CAN NOT*** be reconfigured. If you need to re-assign the Backplane CIDR, you will have to wipe every node, rebuild the cluster, and re-initialize OrbitLab.


### Configuration

Below is the configuration of that Backplane:

- **EVPN Controller**:  Utilizing ASN 65001 and all Proxmox Node IPs (taken from their `vmbr0` device).
- **EVPN Zone**: Using the aforementioned controller and the following settings (settings not listed use the Proxmox default settings):
  - **VRF-VXLAN TAg**: 10
  - **Exit Nodes**: All Proxmox Nodes.
  - **Advertising Subnets**: Yes 
  - **MTU**: The MTU of the `vmbr0` device minus 50.
- **VNet & Subnet**: Defining the actual Backplane boundaries using these settings:
  - **VNet Tag**: 100
  - **Subnet CIDR**: Configured at OrbitLab initialization. User's may set a custom CIDR to ensure no overlap with existing networks, but is set to use `10.200.0.0/16` by default. ***Once set, this is not re-configurable.***
  - **Subnet Gateway**: Using the Subnet CIDR block + 1. For example, a subnet of `172.16.0.0/16` yields `172.16.0.1`, and `10.200.0.0/16` yields `10.200.0.1`.

### Resource Usage

Since the Backplane only consists of Proxmox SDN resources, no actual memory/CPU utilization is calculable. It will obviously consume some CPU and memory resources to perform the network traffic management, but it should be negligible. 

## Sector

When a user creates a Sector, OrbitLab creates a new VXLAN Zone and associated VNet in Proxmox, then attaches a Sector Gateway to facilitate network connectivity between instances in the Sector and the Backplane.

### Configuration

Below is the Proxmox resources created for a Sector:

- **VXLAN Zone**: Defines the network boundaries using these settings (settings not listed use the Proxmox default settings):
  - **Peer Address List**: Taken from the Backplane EVPN Controller settings.
  - **MTU**: Taken from the Backplane MTU configuration.
- **VNet**: Defines the virtual network attachable to compute instances. The VLAN Tag is set to the lowest available between 1001 - 9999.
- **Sector Gateway**: Acts as the Default Gateway for the Sector and facilitates connectivity between the Sector and the Backplane.
- **Sector DNS**: In-Sector hostname resolution.

> NOTE: Sector Gateway are stateful. This means all ingress/egress traffic is pinned to the same router instance.

### Resource Usage

When creating a Sector in OrbitLab, a Sector Gateway (FRR/NFtables) LXC and a Sector DNS (CoreDNS) LXC are created. Since the Sector Gateway is performing static routing only (no BGP/OSPF/EVPN/VRFs), it should sufficiently run on **128 MiB**. The Sector DNS performs basic in-Sector hostname resolution which also sufficiently runs on **128 MiB** of memory. This results in a memory requirement of around **256 MiB**, which is sufficient enough to run even on resource constrained hardware.

> NOTE: FRR in the Sector Gateway is used purely as a lightweight routing daemon. Dynamic protocols are intentionally disabled to keep Sector Gateways deterministic. Also, The Sector Gateway performs coarse DNAT ***ONLY***. If a home LAN resolvable endpoint is required, you must create a Sector Load Balancer (HAproxy) and attach the required VMs/LXCs to it.

### Sector Traffic Flow

Traffic leaving the Backplane follows the Proxmox node’s default routing configuration.

Since the traffic source originates from within the Sector, the network path-back is known. Traffic originating outside the Sector will not resolve to in-Sector resources unless specific ingress paths are created, e.g. a Sector Load Balancer (HAproxy).

```
┌─────────────────────────────────────────────────────────────┐
│                     USER-CREATED SECTOR                     │
│             (Isolated, overlapping CIDRs allowed)           │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │   APP VM / LXC                                        │  │
│  │                                                       │  │
│  │   IP: 172.16.0.42                                     │  │
│  │   GW: 172.16.0.1                                      │  │
│  └───────────────┬───────────────────────────────────────┘  │
│                  │  L3 packet (VXLAN L2 frame)              │
│                  ▼                                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │   SECTOR GATEWAY                                      │  │
│  │                                                       │  │
│  │   eth0 (Sector):     172.16.0.1                       │  │
│  │   gw0  (Sector):     NONE                             │  │
│  │                                                       │  │
│  │   eth1 (Backplane):  10.200.0.10                      │  │
│  │   gw1  (Backplane):  10.200.0.1                       │  │
│  │                                                       │  │
│  └───────────────┬───────────────────────────────────────┘  │
│                  │  NAT-ed packet                           │
└──────────────────┼──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              BACKPLANE NETWORK (Cluster-wide)               │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │   Proxmox Node                                        │  │
│  │                                                       │  │
│  │   Backplane                                           │  │
│  │   IP: 10.200.0.1                                      │  │
│  │                                                       │  │
│  └───────────────┬───────────────────────────────────────┘  │
│                  │  Routed packet                           │
└──────────────────┼──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                 External Destination                        │
│                                                             │
│   Examples:                                                 │
│     - Internet (8.8.8.8)                                    │
│     - Home LAN service (172.16.1.50)                        │
│     - OrbitLab infra service                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Sector Gateways

The Sector Gateway utilizes nftables to provide SNAT/DNAT on ingress/egress traffic. This allows for creating multiple isolated Sectors, even with overlapping CIDR blocks. The FRR implementation used by the Sector Gateway is what routes the traffic across the necessary interfaces.

#### Why not BGP in Sector Gateways?

Sector Gateways intentionally do not run BGP (or any dynamic routing protocol). This is a deliberate design choice rooted in determinism, fault isolation, and operational simplicity.

- **Deterministic Routing**: Sector Gateways exist to provide predictable L3 connectivity between a Sector and the Backplane. Static routes guarantee a single, well-defined egress path, no route convergence delays, and no unexpected path changes due to control-plane events. Dynamic routing would introduce non-determinism into a component whose sole responsibility is controlled translation and forwarding.

- **Overlapping CIDR Isolation**: OrbitLab explicitly allows overlapping CIDR blocks between Sectors as IP address space management can cause headaches for some home lab users. BGP is fundamentally ill-suited for this model because identical prefixes from different Sectors would collide, policy-based routing and VRFs would be required everywhere, and route leaks become a real operational risk. By using NAT at the Sector Gateway boundary, overlapping address spaces remain fully isolated without global routing awareness.

- **Failure Domain Containment**: Sector Gateways are intentionally small and stateful. While a gateway failure is a low but non-zero probability, a gateway failure impacts only its Sector preventing cascading failures across the cluster. Introducing BGP would couple Sector Gateways into a shared control plane, expanding the blast radius of misconfiguration or failure.

- **Resource Efficiency**: Sector Gateways use static routing and nftables which are designed to run on stupidly small amounts of memory. BGP daemons add memory, CPU, and operational overhead, and route churn and timers provide no tangible benefit in this role.

- **Clear Separation of Responsibilities**: Sector Gateways are not routers in the traditional sense. They are controlled translation boundaries. Dynamic routing belongs in the Backplane, where global topology awareness is required.

***TL;DR***: Sector Gateways trade routing flexibility for strict determinism and isolation by design.

#### Configs

##### NFTables

The `/etc/nftables.conf` rules defined below provide DNAT translation during egress (*prerouting*) and SNAT translation for ingress (*postrouting*).

```
table ip nat {
  chain prerouting {
    type nat hook prerouting priority -100;
    iif "eth1" ip daddr $BACKPLANE_NETWORK dnat to $PRIMARY_SECTOR_GATEWAY_IP
    iif "eth0" ip daddr $BACKPLANE_NETWORK drop
  }
  chain postrouting {
    type nat hook postrouting priority 100;
    oif "eth1" masquerade
  }
}
```

##### FRR

The `/etc/frr/frr.conf` configuration below defines routing within the VNet network segment, so VMs/LXCs can talk to one another inside the same VNet, 

```
frr defaults traditional
hostname $SECTOR_GATEWAY_HOSTNAME
log syslog informational
no ipv6 forwarding
ip forwarding
!
interface eth0
 ip address $SECTOR_GATEWAY_SUBNET_ADDRESS
 ... # Repeat the above line N times, one for each subnet in the sector.
 no shutdown
!
interface eth1
 ip address $SECTOR_GATEWAY_BACKPLANE_ADDRESS
 no shutdown
!
ip route 0.0.0.0/0 $BACKPLANE_DEFAULT_GATEWAY
!
end
```

| Variable | Description | Value |
| - | - | - |
| `$SECTOR_GATEWAY_HOSTNAME` | The hostname of the Sector Gateway | `olvn` + the VLAN tag + `-router` |
| `$SECTOR_GATEWAY_SECTOR_ADDRESS` | The default gateway of the Sector | `X.X.X.1/MASK` |
| `$SECTOR_GATEWAY_BACKPLANE_ADDRESS` | The Backplane address of the Sector Gateway | Typically assigned from `10.200.0.0/16` |
| `$BACKPLANE_DEFAULT_GATEWAY` | The default gateway of the Backplane | Typically `10.200.0.1` |

