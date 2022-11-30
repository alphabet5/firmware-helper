# firmware-helper - A python tool to help with updating firmware on network infrastructure devices.

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Overview

fw is a tool to help collect information and transfer images to a large number of network infrastructure devices.

## Usage

```
% python3.11 fw/fw.py --help
usage: fw.py [-h] [--user USER] [--password PASSWORD] [--enable ENABLE] [--list LIST] [--parallel PARALLEL]
             [--delay DELAY] [--driver DRIVER] [--confirm-transfer] [--output OUTPUT]
             function

Utility to help with firmware upgrades of network infrastructure devices.

positional arguments:
  function             Function to run. fetch: fetch information from the list of devices. parse: parse
                       output.json (--output) to hostname, ip, model, image, version, boot-file, and free-
                       space in output.txt. check-transport: check transport connectivity to the list of
                       devices. (telnet or ssh) transfer: verify files have been transferred, and copy files
                       that have not been transferred.

options:
  -h, --help           show this help message and exit
  --user USER          Username for logging into the devices.
  --password PASSWORD  Password for logging into the devices.
  --enable ENABLE      Enable password for the devices.
  --list LIST          File containing the list of devices, of list of devices and files to transfer. Default:
                       ./switch-list.txt
  --parallel PARALLEL  Number of threads to run in parallel. Default: 80
  --delay DELAY        Global delay factor for timeouts. Default: 10
  --driver DRIVER      Napalm driver to use. Default: ios
  --confirm-transfer   Disable dry-run mode, and allow copying of files.
  --output OUTPUT      File to save the output data to. Default 'output.json'
```

### List Format

For fetching information, the list of devices should just be the hostname/ip address of the devices.

```text
192.168.1.1
192.168.1.2
192.168.1.3
```

When transferring files, the list should be a tab-delimited file with hostname/ip, version, source file, file size, md5.

```text
192.168.1.254	15.2(7)E7	ftp://192.168.1.143/c2960x-universalk9-mz.152-7.E7.bin	26788864	1b3781db619dcce6a2677628acc15439
```

### Collecting information from devices.

```bash
% python3.11 fw/fw.py --user username --password password fetch                       
Connecting to 192.168.1.254
Running commands on 192.168.1.254
Running 'get_facts' on 192.168.1.254
Information collection for 192.168.1.254 complete.
prsw01eyotamn   192.168.1.254   WS-C2960X-48TS-L        C2960X-UNIVERSALK9-M    15.2(7)E5       /c2960x-universalk9-mz.152-7.E5/c2960x-universalk9-mz.152-7.E5.bin53046784
```

### Verifying Firmware with a dry-run.

```bash
% python3.11 fw/fw.py --user username --password password --list transfer.csv transfer
Connecting to 192.168.1.254
Running commands on 192.168.1.254
Running 'get_facts' on 192.168.1.254
Beginning file verification on 192.168.1.254
Verification ~17% complete on 192.168.1.254 Estimated Time Remaining: 0:00:24.665015
Verification ~35% complete on 192.168.1.254 Estimated Time Remaining: 0:00:18.912943
Verification ~53% complete on 192.168.1.254 Estimated Time Remaining: 0:00:13.463153
Verification ~71% complete on 192.168.1.254 Estimated Time Remaining: 0:00:08.110668
Verification ~90% complete on 192.168.1.254 Estimated Time Remaining: 0:00:02.782539
File ftp://192.168.1.143/c2960x-universalk9-mz.152-7.E7.bin on device 192.168.1.254 has been verified. Ready for upgrade.
```

### Transferring Firmware

```bash
% python3.11 fw/fw.py --user username --password password --list transfer.csv --confirm-transfer transfer
Connecting to 192.168.1.254
Running commands on 192.168.1.254
Running 'get_facts' on 192.168.1.254
Beginning file copy on 192.168.1.254
Copy ~2% complete on 192.168.1.254 Estimated Time Remaining: 0:07:23.401429
Copy ~3% complete on 192.168.1.254 Estimated Time Remaining: 0:07:42.210385
Copy ~5% complete on 192.168.1.254 Estimated Time Remaining: 0:06:11.642711
...
Copy ~97% complete on 192.168.1.254 Estimated Time Remaining: 0:00:10.214569
Copy ~98% complete on 192.168.1.254 Estimated Time Remaining: 0:00:06.369473
Copy ~99% complete on 192.168.1.254 Estimated Time Remaining: 0:00:02.502097
File copy for 192.168.1.254 completed in -1 day, 23:53:05.925660
Destination filename [c2960x-universalk9-mz.152-7.E7.bin]? Accessing ftp://192.168.1.143/c2960x-universalk9-mz.152-7.E7.bin...
Loading c2960x-universalk9-mz.152-7.E7.bin !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
[OK - 26788864/4096 bytes]

26788864 bytes copied in 403.800 secs (66342 bytes/sec)
prsw01eyotamn#
Beginning file verification on 192.168.1.254
Verification ~17% complete on 192.168.1.254 Estimated Time Remaining: 0:00:24.045258
Verification ~35% complete on 192.168.1.254 Estimated Time Remaining: 0:00:18.622919
Verification ~52% complete on 192.168.1.254 Estimated Time Remaining: 0:00:13.693716
Verification ~71% complete on 192.168.1.254 Estimated Time Remaining: 0:00:08.223775
Verification ~90% complete on 192.168.1.254 Estimated Time Remaining: 0:00:02.900680
File ftp://192.168.1.143/c2960x-universalk9-mz.152-7.E7.bin on device 192.168.1.254 has been verified. Ready for upgrade.
```

## Offline Installation for Windows

To download all of the recursive dependencies use `python3 -m pip download --platform win_amd64 --no-deps`.

The python version from the system you are running, should match the destination python version. 

```bash
% python3 --version
Python 3.10.8
```

If `python3` is a different version, install a matching version, and use the specific command for that version of python.

```bash
% python3.11 --version
Python 3.11.0
```
->
```bash
python3.11 -m pip download --platform win_amd64 --no-deps
```

```bash
python3 -m pip download --platform win_amd64 --no-deps napalm PyYAML future jinja2 transitions pynacl bcrypt netaddr toml loguru charset-normalizer==2.1.1 pyparsing textfsm==1.1.2 ciscoconfparse junos-eznc paramiko tenacity urllib3 yamlordereddictloader pycparser netmiko scp cffi idna MarkupSafe ncclient lxml pyeapi certifi dnspython six passlib requests cryptography ntc-templates pyserial setuptools win32_setctime netutils colorama typing-extensions ttp ttp-templates chardet rich
```

Copy these files to the offline machine, and install them.

```text
cd C:\your\directory\
python -m pip install *
```

## Changelog

### 0.0.1 - Initial Release
- Support for Cisco devices added.

### 0.0.2
- Support other prompts when switches are configured for an interactive terminal.
- Added 10k '!' value for progress when using scp.


### 0.0.3
- Cleaned up inaccurate comments.
- Enabled direct call of the parsing function.