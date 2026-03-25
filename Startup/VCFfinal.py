# VCFfinal.py version 1.4 2026-03-25
import datetime
import os
import sys
from pyVim import connect
from pyVmomi import vim
import logging
import requests
import urllib3
import lsfunctions as lsf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SDDC = 'sddcmanager-a.site-a.vcf.lab'
STALE_CREDENTIAL_PATTERNS = [
    'svc-sddcmanager-a-nsx-mgmt-',
    'svc-sddcmanager-a-nsx-wld01-',
]


def cleanup_stale_sddc_credentials():
    """
    Remove stale NSX service account credentials from SDDC Manager.
    These accounts no longer exist but cause error banners in vCenter.
    Deletion must be done via direct PostgreSQL access since the
    SDDC Manager REST API does not support DELETE on credentials.
    Uses a self-contained Python script SCP'd to SDDC Manager to avoid
    shell quoting issues with lsf.ssh().
    Stale accounts were
    svc-sddcmanager-a-nsx-mgmt--5825
    svc-sddcmanager-a-nsx-wld01-1894
    """
    pw = lsf.password

    try:
        resp = requests.post(
            f'https://{SDDC}/v1/tokens',
            json={'username': 'admin@local', 'password': pw},
            verify=False, timeout=30
        )
        if resp.status_code != 200:
            lsf.write_output(f'SDDC credential cleanup: cannot get token (HTTP {resp.status_code}), skipping')
            return
        token = resp.json().get('accessToken', '')
    except Exception as e:
        lsf.write_output(f'SDDC credential cleanup: token request failed ({e}), skipping')
        return

    try:
        resp = requests.get(
            f'https://{SDDC}/v1/credentials',
            headers={'Authorization': f'Bearer {token}'},
            verify=False, timeout=30
        )
        elements = resp.json().get('elements', [])
    except Exception as e:
        lsf.write_output(f'SDDC credential cleanup: credentials query failed ({e}), skipping')
        return

    stale = [el for el in elements
             if any(el.get('username', '').startswith(pat) for pat in STALE_CREDENTIAL_PATTERNS)]

    if not stale:
        lsf.write_output('SDDC credential cleanup: no stale NSX service accounts found')
        return

    stale_names = [el['username'] for el in stale]
    stale_ids = [el['id'] for el in stale]
    lsf.write_output(f'SDDC credential cleanup: found {len(stale)} stale account(s): {", ".join(stale_names)}')

    local_script = '/tmp/sddc_cred_cleanup.py'
    remote_script = '/tmp/sddc_cred_cleanup.py'

    script_lines = [
        'import pty, os, time, sys, json',
        '',
        'PW = ' + repr(pw),
        'IDS = ' + repr(stale_ids),
        '',
        'def su_root_cmd(commands):',
        '    m, s = pty.openpty()',
        '    pid = os.fork()',
        '    if pid == 0:',
        '        os.setsid()',
        '        os.dup2(s, 0); os.dup2(s, 1); os.dup2(s, 2); os.close(m)',
        '        os.execvp("su", ["su", "-", "root"])',
        '    time.sleep(1)',
        '    os.write(m, (PW + "\\n").encode())',
        '    time.sleep(1)',
        '    for cmd in commands:',
        '        os.write(m, (cmd + "\\n").encode())',
        '        time.sleep(2)',
        '    os.write(m, b"exit\\n")',
        '    time.sleep(0.5)',
        '    data = os.read(m, 16384).decode(errors="ignore")',
        '    os.waitpid(pid, 0)',
        '    return data',
        '',
        'output = su_root_cmd(["cat /root/.pgpass"])',
        'pgpass = ""',
        'for line in output.splitlines():',
        '    if line.startswith("localhost") and "postgres:" in line:',
        '        pgpass = line.split(":")[-1]',
        '        break',
        '',
        'if not pgpass:',
        '    print("ERROR: could not extract pgpass")',
        '    sys.exit(1)',
        '',
        "id_list = ','.join(\"'\" + cid + \"'\" for cid in IDS)",
        'sql = "DELETE FROM credentialhistory WHERE credential_id IN (" + id_list + "); '
        'DELETE FROM credential WHERE id IN (" + id_list + ");"',
        "psql_cmd = \"PGPASSWORD='\" + pgpass + \"' /usr/pgsql/15/bin/psql -h 127.0.0.1 -U postgres -d platform -c \\\"\" + sql + \"\\\"\"",
        '',
        'output = su_root_cmd([psql_cmd])',
        'print("SQL_DONE")',
        'for line in output.splitlines():',
        '    if "DELETE" in line:',
        '        print(line)',
        '',
        'su_root_cmd(["systemctl restart operationsmanager commonsvcs domainmanager"])',
        'print("RESTART_DONE")',
    ]

    with open(local_script, 'w') as f:
        f.write('\n'.join(script_lines) + '\n')

    lsf.scp(local_script, f'vcf@{SDDC}:{remote_script}', pw)
    result = lsf.ssh(f'python3 {remote_script}', f'vcf@{SDDC}', pw)
    lsf.ssh(f'rm -f {remote_script}', f'vcf@{SDDC}', pw)
    try:
        os.remove(local_script)
    except OSError:
        pass

    lsf.write_output(f'SDDC credential cleanup: result: {result.stdout.strip()}')


def verify_nic_connected (vm_obj, simple):
    """
    Loop through the NICs and verify connection
    :param vm: the VM to check
    :param simple: true just connect do not disconnect then reconnect
    """
    nics = lsf.get_network_adapter(vm_obj)
    for nic in nics:
        if simple:
            lsf.write_output(f'Connecting {nic.deviceInfo.label} on {vm.name} .')
            lsf.set_network_adapter_connection(vm, nic, True)
            lsf.labstartup_sleep(lsf.sleep_seconds)
        elif nic.connectable.connected == True:
            lsf.write_output(f'{vm.name} {nic.deviceInfo.label} is connected.')
        else:
            lsf.write_output(f'{vm.name} {nic.deviceInfo.label} is NOT connected.')
            lsf.set_network_adapter_connection(vm, nic, False)
            lsf.labstartup_sleep(lsf.sleep_seconds)
            lsf.write_output(f'Connecting {nic.deviceInfo.label} on {vm.name} .')
            lsf.set_network_adapter_connection(vm, nic, True)

# read the /hol/config.ini
lsf.init(router=False)

# verify a VCFfinal section exists
if lsf.config.has_section('VCFFINAL') == False:
    lsf.write_output('Skipping VCF final startup')
    exit(0)

color = 'red'
if len(sys.argv) > 1:
    lsf.start_time = datetime.datetime.now() - datetime.timedelta(seconds=int(sys.argv[1]))
    if sys.argv[2] == "True":
        lsf.labcheck = True
        color = 'green'
        lsf.write_output(f'{sys.argv[0]}: labcheck is {lsf.labcheck}')   
    else:
        lsf.labcheck = False
 
lsf.write_output(f'Running {sys.argv[0]}')
lsf.write_vpodprogress('Tanzu Start', 'GOOD-8', color=color)

### Start SupervisorControlPlaneVMs
vcfmgmtcluster = []
if 'vcfmgmtcluster' in lsf.config['VCF'].keys():
    vcfmgmtcluster = lsf.config.get('VCF', 'vcfmgmtcluster').split('\n')
    lsf.write_vpodprogress('VCF Hosts Connect', 'GOOD-3', color=color)
    lsf.connect_vcenters(vcfmgmtcluster)

lsf.write_vpodprogress('Tanzu Control Plane', 'GOOD-8', color=color)
supvms = lsf.get_vm_match('Supervisor*')
for vm in supvms:
   lsf.write_output(f'{vm.name} is {vm.runtime.powerState}')
   try:
        if vm.runtime.powerState != "poweredOn":
            lsf.start_nested([f'{vm.name}:{vm.runtime.host.name}'])
   except Exception as e:
        lsf.write_output(f'exception: {e}')

### Reconnect SupervisorControlPlaneVM NICs
for vm in supvms:
    verify_nic_connected (vm, False) # if not connected, disconnet then reconnect

## Restart Supervisor Webhooks to make sure certificate is valid/renewed
# if supvms list is not empty, then restart the webhooks
if supvms:
    lsf.write_output(f'Restarting Supervisor Webhooks')
    lsf.run_command("/home/holuser/hol/Tools/restart_k8s_webhooks.sh")
                
# Wizardry to deploy Tanzu

tanzucreate = []
if 'tanzucreate' in lsf.config['VCFFINAL'].keys():
    lsf.write_vpodprogress('Deploy Tanzu (25 Minutes)', 'GOOD-8', color=color)
    lsf.write_output('Deploy Tanzu (25 Minutes)')
    tanzucreate = lsf.config.get('VCFFINAL', 'tanzucreate').split('\n')
    lsf.write_vpodprogress('Waiting for Tanzu img to populate', 'GOOD-8', color=color)
    lsf.write_output('Waiting for Tanzu Images (10 minutes)...')
    # DEBUG skip this for dev testing - is there a test we can do?
    lsf.labstartup_sleep(600)

    # centos machine is 10.0.0.3 /root/TanzuCreate script. recommend DNS entry
    (tchost, tcaccount, tcscript) = tanzucreate[0].split(':')
    lsf.write_output(f'Running {tcscript} as {tcaccount}@{tchost} with password lsf.password')
    # DEBUG comment out
    result = lsf.ssh(tcscript, f'{tcaccount}@{tchost}', lsf.password, logfile=lsf.logfile)
    lsf.write_output(result.stdout)

######Start Aria Automation VMs
# Could we start this during the 10 minutes we're waiting for Tanzu?
vravms = []
if 'vravms' in lsf.config['VCFFINAL'].keys():
    vcenters = []
    if 'vCenters' in lsf.config['RESOURCES'].keys():
        vcenters = lsf.config.get('RESOURCES', 'vCenters').split('\n')

    if vcenters:
        lsf.write_vpodprogress('Connecting vCenters', 'GOOD-3', color=color)
        lsf.connect_vcenters(vcenters)
    vravms = lsf.config.get('VCFFINAL', 'vravms').split('\n')
    lsf.write_output('Starting Workspace Access...')
    lsf.write_vpodprogress('Starting Workspace Access', 'GOOD-8', color=color)
    # before starting verify NICs are set to start connected
    for vravm in vravms:
        (vmname, server) = vravm.split(':')
        try:
            vms = lsf.get_vm_match(vmname)
            for vm in vms:
                verify_nic_connected (vm, True) # just make sure connected at start
        except Exception as e:
            lsf.write_output(f'{e}')
    lsf.start_nested(vravms)
    # verify that the wsa L2 VM is actually starting
    # after starting verify NIC is actually connected
    for vravm in vravms:
        (vmname, server) = vravm.split(':')
        vms = lsf.get_vm_match(vmname)
        for vm in vms:
            while vm.runtime.powerState != 'poweredOn':
                vm.PowerOnVM_Task()
                lsf.labstartup_sleep(lsf.sleep_seconds)
            while vm.summary.guest.toolsRunningStatus != 'guestToolsRunning':
                lsf.write_output(f'Waiting for Tools in {vmname}...')
                lsf.labstartup_sleep(lsf.sleep_seconds)
                verify_nic_connected (vm, False) # if not connected, disconnect and reconnect
    
##### Final URL Checking
vraurls = []
if 'vraurls' in lsf.config['VCFFINAL'].keys():
    vraurls = lsf.config.get('VCFFINAL', 'vraurls').split('\n')
    lsf.write_vpodprogress('Aria Automation URL Checks', 'GOOD-8', color=color)
    lsf.write_output('Aria Automation URL Checks...')
    # Check VCF Automation ssh for password expiration and fix if expired
    lsf.write_output('Fixing expired automation pw if necessary...')
    lsf.run_command("/home/holuser/hol/Tools/vcfapwcheck.sh")
    # Run the watchvcfa script to make sure the seaweedfs-master-0 pod is not stale
    lsf.run_command("/home/holuser/hol/Tools/watchvcfa.sh")

    for entry in vraurls:
        url = entry.split(',')
        lsf.write_output(f'Testing {url[0]} for pattern {url[1]}')
        #  not_ready: optional pattern if present means not ready verbose: display the html
        #  lsf.test_url(url[0], pattern=url[1], not_ready='not yet', verbose=True)
        ctr = 0
        while not lsf.test_url(url[0], pattern=url[1], timeout=2, verbose=False):
            ctr += 1
            # If the URL is still unreachable after 30m, even with remediation attempt, then fail the pod
            if ctr == 30:
                lsf.labfail('fail: Automation URLS not accessible after 30m, should be reached in under 8m')
                exit(1)
                # Try to prevent excessive logging while waiting for VLP to stop vApp
                lsf.labstartup_sleep(120)
            # Wait for 1m before retrying
            lsf.write_output(f'Sleeping and will try again... {ctr} / 30')
            lsf.labstartup_sleep(60)             

### Clean up stale SDDC Manager credentials that cause vCenter error banners
cleanup_stale_sddc_credentials()

for si in lsf.sis:
    connect.Disconnect(si)

lsf.write_output(f'{sys.argv[0]} finished.')
 