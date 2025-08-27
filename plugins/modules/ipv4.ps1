#!powershell

#Requires -Module Ansible.ModuleUtils.Legacy

$ErrorActionPreference = "Stop"

$params = Parse-Args $args -supports_check_mode $true;

$adapterName = Get-AnsibleParam -obj $params -name adapter_name -default "Ethernet"
$ipAddr = Get-AnsibleParam -obj $params -name ip_address
$ipPrefix = Get-AnsibleParam -obj $params -name ip_prefix
$gwAddr = Get-AnsibleParam -obj $params -name ip_gateway
$nsAddr = Get-AnsibleParam -obj $params -name ip_nameserver

$state = Get-AnsibleParam -obj $params -name state -default "present"

$result = @{
    changed = $false
}

function SetIPAddress {
    Write-Verbose -Message "Setting IP address to $ipAddr"

    $ipParams = @{
        IPAddress = $ipAddr
        PrefixLength = $ipPrefix
        DefaultGateway = $gwAddr
    }
    Get-NetAdapter -Name $adapterName | ForEach-Object {
        $_ | Set-NetIPInterface -Dhcp Disabled
        $ips = $_ | Get-NetIPAddress
        $ips | Where-Object {$_.IPAddress -ne $ipAddr} | Remove-NetIPAddress -Confirm:$false
        if ($ipAddr -notin $ips.IPAddress) {
            $result.changed = $true
            Get-NetRoute -NextHop $gwAddr -ErrorAction Ignore | Remove-NetRoute -Confirm:$false
            $null = $_ | New-NetIPAddress @ipParams
        }

        $ns = $_ | Get-DnsClientServerAddress
        if ($nsAddr -notin $ns.ServerAddresses) {
            $result.changed = $true
            $null = $_ | Set-DnsClientServerAddress -ServerAddresses $nsAddr
        }
    }
}

function RemoveIPAddress {
    Write-Verbose -Message "Removing IP address"

    Get-NetAdapter -Name $adapterName | ForEach-Object {
        $ips = $_ | Get-NetIPAddress
        $ips | Where-Object {$_.IPAddress -eq $ipAddr} | ForEach-Object {
            $result.changed = $true
            $null = $_ | Remove-NetIPAddress -Confirm:$false
        }
    }
}

switch ($state) {
    "present" { SetIPAddress }
    "absent" { RemoveIPAddress }
}

Exit-Json $result
