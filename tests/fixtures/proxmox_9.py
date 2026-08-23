"""Representative Proxmox VE 9 API responses used by adapter-level tests."""

CLUSTER_RESOURCES = [
    {"vmid": 101, "node": "pve-a", "type": "lxc", "status": "running", "name": "ol-gateway"},
    {"vmid": 102, "node": "pve-b", "type": "qemu", "status": "stopped", "name": "ol-dockfs"},
]

TASK_STATUS = {
    "starttime": 1_735_689_600,
    "pid": 12345,
    "node": "pve-a",
    "pstart": 1,
    "type": "vzdump",
    "upid": "UPID:pve-a:00003039:00000001:67600000:vzdump:101:root@pam:",
    "status": "stopped",
    "id": "101",
    "user": "root@pam",
    "exitstatus": "OK",
}

STORAGE = [
    {
        "storage": "local-lvm",
        "type": "lvmthin",
        "active": 1,
        "enabled": 1,
        "shared": 0,
        "content": "images,rootdir",
        "avail": 1000000,
        "total": 2000000,
        "used": 1000000,
        "used_fraction": 0.5,
    },
]

CLUSTER_STATUS = [
    {"type": "cluster", "name": "lab", "quorate": 1, "version": 12, "nodes": 2},
    {"type": "node", "nodeid": 1, "local": 1, "online": 1, "ip": "192.0.2.10", "name": "pve-a"},
    {"type": "node", "nodeid": 2, "local": 0, "online": 1, "ip": "192.0.2.11", "name": "pve-b"},
]

BRIDGES = [
    {"active": 1, "address": "192.0.2.10", "autostart": 1, "cidr": "192.0.2.10/24", "iface": "vmbr0"},
]

VNets = [
    {"vnet": "orbitlab", "tag": 120, "zone": "orbitlab", "alias": "OrbitLab Backplane"},
    {"vnet": "pending", "tag": 0, "pending": {"tag": "121"}, "zone": "pending"},
]

SDN_CONTROLLERS = [
    {"type": "evpn", "controller": "orbitlab", "asn": 65001, "peers": "192.0.2.10,192.0.2.11"},
]
