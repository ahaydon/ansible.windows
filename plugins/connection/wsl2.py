from __future__ import annotations

import os
import pty
import shutil
import subprocess
import typing as t

from ansible.errors import AnsibleError
from ansible.errors import AnsibleFileNotFound
from ansible.module_utils.six import text_type, binary_type
from ansible.module_utils.common.text.converters import to_bytes, to_native, to_text
from ansible.playbook.play_context import PlayContext
from ansible.plugins.become import BecomeBase
from ansible.plugins.connection import ConnectionBase
from ansible.plugins.shell.powershell import ShellModule as PowerShellPlugin
from ansible.utils.display import Display

DOCUMENTATION = """
author: Adam Haydon
name: wsl2
short_description: Run tasks on WSL host or in a VM with Hyper-V integration services
description:
- Run commands or put/fetch on a target via WSL or Hyper-V integration services.
version_added: "2.7"
extends_documentation_fragment:
- connection_pipelining
options:
  # transport options
  remote_addr:
    description:
    - The hostname or IP address of the remote host.
    default: inventory_hostname
    type: str
    vars:
    - name: inventory_hostname
    - name: ansible_host
    - name: ansible_psrp_host
  vm_name:
    description:
    - The hostname or IP address of the remote host.
    type: str
    vars:
    - name: ansible_vm_name
  remote_user:
    description:
    - The user to log in as.
    type: str
    vars:
    - name: ansible_user
    - name: ansible_wsl_user
    keyword:
    - name: remote_user
  remote_password:
    description: Authentication password for the O(remote_user). Can be supplied as CLI option.
    type: str
    vars:
    - name: ansible_password
    - name: ansible_wsl_password
    aliases:
    - password  # Needed for --ask-pass to come through on delegation

  # protocol options
  operation_timeout:
    description:
    - Sets the WSL timeout for each operation.
    - This is measured in seconds.
    - This should not exceed the value for O(connection_timeout).
    type: int
    vars:
    - name: ansible_wsl_operation_timeout
    default: 20
  configuration_name:
    description:
    - The name of the PowerShell configuration endpoint to connect to.
    type: str
    vars:
    - name: ansible_wsl_configuration_name
    default: Microsoft.PowerShell
"""

ENTER_VM = """
# $WarningPreference = 'SilentlyContinue'
$secpass = ConvertTo-SecureString -AsPlainText -Force -String '{2}'
$cred = [PSCredential]::new('{1}', $secpass)
$exec_wrapper_str = $input | Out-String
$cmd = [ScriptBlock]::Create(@'
{3}
'@)
$s = New-PSSession -VMName '{0}' -Credential $cred
Invoke-Command -Session $s -InputObject $exec_wrapper_str -ScriptBlock $cmd
$s | Remove-PSSession
"""

COPY_FILE = """
$secpass = ConvertTo-SecureString -AsPlainText -Force -String '{2}'
$cred = [PSCredential]::new('{1}', $secpass)
$s = New-PSSession -VMName '{0}' -Credential $cred
Copy-Item -ToSession $s -Path '{3}' -Destination '{4}'
$s | Remove-PSSession
"""

display = Display()


class Connection(ConnectionBase):
    module_implementation_preferences = (".ps1", ".exe", "")
    allow_executable = False
    has_pipelining = True
    allow_extras = True
    _play_context: PlayContext
    become: BecomeBase | None = None

    # Satifies mypy as this connection only ever runs with this plugin
    _shell: PowerShellPlugin

    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        self.always_pipeline_modules = True
        self.has_native_async = True

        self.cwd = None

        self._shell_type = "powershell"
        super(Connection, self).__init__(*args, **kwargs)

    @property
    def transport(self) -> str:
        """String used to identify this Connection class from other classes"""
        return "wsl2"

    def _connect(self) -> Connection:
        """connect to the local host; nothing to do here"""

        if not self._connected:
            display.vvv(
                "ESTABLISH LOCAL CONNECTION FOR USER: {0}".format(
                    self._play_context.remote_user
                ),
                host=self._play_context.remote_addr,
            )
            self._connected = True
        return self

    def exec_command(
        self, cmd: str | bytes, in_data: bytes | None = None, sudoable: bool = True
    ) -> tuple[int, bytes, bytes]:
        """run a command on the local host"""

        display.vvvvv(f"CMD: {to_text(cmd)}")
        display.vv(f"EXE: {to_text(self._play_context.executable)}")
        display.vv(f"VM: {self.get_option('vm_name')}")
        display.vvvvvv(f"IN: {in_data}")
        super(Connection, self).exec_command(
            str(cmd), in_data=in_data, sudoable=sudoable
        )

        display.debug("in local.exec_command()")

        executable = shutil.which("powershell.exe") or "powershell.exe"
        display.vv(f"SHELL: {to_text(executable)}")

        if not os.path.exists(to_bytes(executable, errors="surrogate_or_strict")):
            raise AnsibleError(
                "failed to find the executable specified %s."
                " Please verify if the executable exists and re-try." % executable
            )

        display.vvv(
            "EXEC {0}".format(to_text(cmd)), host=self._play_context.remote_addr
        )
        display.debug("opening command with Popen()")

        if isinstance(cmd, (text_type, binary_type)):
            cmd = to_bytes(cmd)
        else:
            cmd = str(map(to_bytes, cmd))

        master = None
        stdin = subprocess.PIPE
        if (
            sudoable
            and self.become
            and self.become.expect_prompt()
            and not self.get_option("pipelining")
        ):
            # Create a pty if sudoable for privilege escalation that needs it.
            # Falls back to using a standard pipe if this fails, which may
            # cause the command to fail in certain situations where we are escalating
            # privileges or the command otherwise needs a pty.
            try:
                master, stdin = pty.openpty()
            except (IOError, OSError) as e:
                display.debug("Unable to open pty: %s" % to_native(e))

        if self.get_option("vm_name"):
            connect_script = ENTER_VM.format(
                self.get_option("vm_name"),
                self._play_context.remote_user,
                self._play_context.password,
                to_text(cmd),
            )
            display.vv(connect_script)
            cmd = to_bytes(connect_script)

        p = subprocess.Popen(
            cmd,
            shell=isinstance(cmd, (text_type, binary_type)),
            executable=executable,
            cwd=self.cwd,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # if we created a master, we can close the other half of the pty now, otherwise master is stdin
        if master is not None:
            os.close(stdin)

        display.debug("done running command with Popen()")

        display.debug("getting output with communicate()")
        stdout, stderr = p.communicate(in_data)
        display.v(to_text(stdout))
        display.v(to_text(stderr))
        display.debug("done communicating")

        # finally, close the other half of the pty, if it was created
        if master:
            os.close(master)

        display.debug("done with local.exec_command()")
        return (p.returncode, stdout, stderr)

    def put_file(self, in_path: str, out_path: str) -> None:
        """transfer a file from local to local"""

        super(Connection, self).put_file(in_path, out_path)

        if not os.path.exists(to_bytes(in_path, errors="surrogate_or_strict")):
            raise AnsibleFileNotFound(
                "file or module does not exist: {0}".format(to_native(in_path))
            )

        cmd = ["wslpath", "-w", in_path]
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="UTF8",
        )
        stdout, _ = p.communicate()
        in_path = str(stdout)

        display.vvv(
            "PUT {0} TO {1}".format(in_path, out_path),
            host=self._play_context.remote_addr,
        )

        if self.get_option("vm_name"):
            copy_script = COPY_FILE.format(
                self.get_option("vm_name"),
                self._play_context.remote_user,
                self._play_context.password,
                to_text(in_path).rstrip("\n"),
                to_text(out_path),
            )
            display.vv(copy_script)
            cmd = to_bytes(copy_script)

            executable = shutil.which("powershell.exe") or "powershell.exe"
            display.vv(f"SHELL: {to_text(executable)}")

            p = subprocess.Popen(
                cmd,
                shell=isinstance(cmd, (text_type, binary_type)),
                executable=executable,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            display.debug("getting output with communicate()")
            stdout, stderr = p.communicate()
            display.v(to_text(stdout))
            display.v(to_text(stderr))
            display.debug("done communicating")

            return

        try:
            shutil.copyfile(
                to_bytes(in_path, errors="surrogate_or_strict"),
                to_bytes(out_path, errors="surrogate_or_strict"),
            )
        except shutil.Error:
            raise AnsibleError(
                "failed to copy: {0} and {1} are the same".format(
                    to_native(in_path), to_native(out_path)
                )
            )
        except IOError as e:
            raise AnsibleError(
                "failed to transfer file to {0}: {1}".format(
                    to_native(out_path), to_native(e)
                )
            )

    def fetch_file(self, in_path: str, out_path: str) -> None:
        """fetch a file from local to local -- for compatibility"""

        super(Connection, self).fetch_file(in_path, out_path)

        display.vvv(
            "FETCH {0} TO {1}".format(in_path, out_path),
            host=self._play_context.remote_addr,
        )
        self.put_file(in_path, out_path)

    def close(self) -> None:
        self._connected = False
