from typing import Any


DOCUMENTATION = """
---
module: ipv4
version_added: "0.1"
short_description: Adds and deletes IP settings on Windows.
description:
    - Adds and deletes IP settings on Windows.
options:
  state:
    description:
      - State of VM
    required: false
    choices:
      - present
      - absent
	  - running
	  - stopped
      - poweroff
    default: present
  adapter_name:
    description:
      - Specifies a network adapter for the VM
    required: true
  ip_address:
    description:
      - Set the IP address of the guest OS
    required: true
  ip_prefix:
    description:
      - Set the IP prefix of the guest OS
    required: false
  ip_gateway:
    description:
      - Set the IP gateway of the guest OS
    required: false
  ip_nameserver:
    description:
      - Set the IP DNS nameserver of the guest OS
    required: false
"""

EXAMPLES = """
  # Add an IP address to the Enternet interface
  ipv4:
    adapter_name: Ehternet
    ip_address: 192.168.0.1
    ip_prefix: 255.255.255.0
    ip_gateway: 192.168.0.1
    ip_nameserver: 192.168.0.1

  # Delete an IP address
  ipv4:
    adapter_name: Ehternet
    ip_address: 192.168.0.1
	state: absent
"""

ANSIBLE_METADATA: dict[str, Any] = {
    "status": ["preview"],
    "supported_by": "community",
    "metadata_version": "0.1",
}
