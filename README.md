# Ansible Collection for Windows

This collection includes Ansible plugins for Windows and the Windows Subsystem for Linux (WSL).

## Requirements

Tested with Ansible Core >= 2.12.0 versions.

## Installation

The collection can be installed with `ansible-galaxy`:

```sh
ansible-galaxy collection install git+https://github.com/ahaydon/ansible.windows.git
```

## Usage

The plugins can be used to connect to a Windows host from a WSL instance and to connect to Hyper-V virtual machines on the Windows host.

```yaml
all:
  hosts:
    win-server-01:
      ansible_connection: ahaydon.windows.wsl2
```

## License

This Ansible collection is [MIT licensed](LICENSE)