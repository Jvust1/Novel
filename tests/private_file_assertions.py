"""Independent Windows ACL readback via PowerShell, not the writer's helper."""
import json
import os
import subprocess


def assert_windows_private_file(path):
    script = """$ErrorActionPreference='Stop';
    $acl=Get-Acl -LiteralPath $env:NOVEL_TEST_ACL_PATH;
    $rules=@($acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]) | ForEach-Object {
      @{sid=$_.IdentityReference.Value; rights=[int]$_.FileSystemRights;
        type=$_.AccessControlType.ToString(); inherited=$_.IsInherited}
    });
    @{user=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
      owner=$acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value;
      protected=$acl.AreAccessRulesProtected; rules=$rules} | ConvertTo-Json -Depth 5 -Compress
    """
    p = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                       env=dict(os.environ, NOVEL_TEST_ACL_PATH=str(path)),
                       capture_output=True, timeout=30)
    assert p.returncode == 0, p.stderr.decode(errors='backslashreplace')
    value = json.loads(p.stdout)
    assert value['owner'] == value['user']
    assert value['protected'] is True
    assert value['rules'] == [{'sid': value['user'], 'rights': 0x001F01FF,
                               'type': 'Allow', 'inherited': False}]
