"""Constants for OrbitLab."""

from types import SimpleNamespace
from typing import Final


class EventStreams(SimpleNamespace):
    """Constants for OrbitLab event stream identifiers."""

    WORKFLOWS = "ol:workflows"
    EVENTS = "ol:events"
    NOTIFICATIONS = "ol:notifications"
    WORKFLOW_LOGS = "ol:logs:workflows"
    SYSTEM_LOGS = "ol:logs:system"


USER_ACKNOWLEDGEMENT: Final = """
Before OrbitLab can be used, it needs to prepare a small amount of infrastructure inside your Proxmox environment.

OrbitLab will configure a Backplane network using a Proxmox EVPN/BGP VXLAN SDN, create one lightweight OrbitLab 
Backplane LXC, and a 3-node ETCD cluster. The Backplane LXC provides both central DNS for all networks (the backplane 
network and all user-created Sectors) and an HTTP relay used by OrbitLab-managed resources to communicate with the 
OrbitLab. The ETCD Cluster provides central configuration management for OrbitLab-managed resources.

Each LXC is intended to use minimal resources: **1 Core**, **512 MiB** Memory, **512 MiB** Swap, and **8 GiB** of 
disk. For a grand total of **2 GiB** Memory, **2 GiB** Swap, and **32 GiB** of disk space, with the CPU usage being 
distributed across **4 individual CPU Cores**.

You will be required to configure a few cluster defaults, such as which node and storage locations should be used for 
its infrastructure, which can be reconfigured any time after initialization.

OrbitLab touches Proxmox networking and installs packages, such as `frr`, on the Proxmox nodes. So, make sure you are 
comfortable with OrbitLab managing that baseline configuration before continuing.

Review the selected CIDR, ASN, node, and storage settings carefully before continuing, because some Backplane settings 
may not be re-configurable after initialization.
"""
