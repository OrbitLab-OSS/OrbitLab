# from pydantic import RootModel
# from orbitlab.clients.proxmox.base import Proxmox

# class Task(RootModel[str]):
#     """Proxmox Task."""

#     @property
#     def upid(self) -> str:
#         """Get the unique process identifier (UPID) of the task."""
#         return self.root

#     @property
#     def node(self) -> str:
#         """Get the node name from the UPID."""
#         return self.root.split(":")[1]


# proxmox = Proxmox()
# vmid = proxmox.get_next_vmid()
# # sector = SectorManifest.load(name=lxc.spec.sector.name)
# # sector = SectorManifest.load(name="olvn1000")
# # address = sector.get_ipam().assign_ip(subnet_name=lxc.spec.subnet_name, vmid=vmid)
# # address = sector.get_ipam().assign_ip(subnet_name="subnet-1", vmid=vmid)
# # gateway = sector.get_subnet(name="subnet-1").default_gateway
# params = {
#     "vmid": vmid,
#     "name": "test", # MANIFEST
#     "cores": 2, # MANIFEST
#     "sockets": 1, # MANIFEST
#     "memory": 2 * 1024, # MANIFEST
#     "cpu": "x86-64-v2-AES",
#     "numa": 0,
#     "agent": "enabled=1",
#     "scsi0": "local-zfs:0,import-from=local:import/orbitlab-debian-13-amd64-20260117.qcow2", # MANIFEST
#     "ide0": "local-zfs:cloudinit", # MANIFEST
#     "citype": "nocloud",
#     "ciuser": "root", # MANIFEST
#     "cipassword": "asdfasdf", # MANIFEST
#     "net0":	"virtio,bridge=olvn1000", # MANIFEST
#     "ipconfig0": "gw=192.168.0.1,ip=192.168.25.1/18", # MANIFEST
#     "searchdomain": "olvn1000.orbitlab.internal",
#     "nameserver": "192.168.0.2",
#     "scsihw": "virtio-scsi-single",
#     "ostype": "l26",
#     "onboot": "1", # MANIFEST
#     "boot": "order=scsi0",
# }
# task = proxmox.create(f"/nodes/{proxmox.__node__}/qemu", model=Task, **params)
# proxmox.wait_for_task(node=task.node, upid=task.upid)
