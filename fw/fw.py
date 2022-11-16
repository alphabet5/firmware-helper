from napalm import get_network_driver
import re
from ntc_templates import parse
import argparse
import socket
import json
from joblib import Parallel, delayed
import traceback
import netmiko.exceptions


class ConnectivityFailure(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(
        description="Utility to help with firmware upgrades of network infrastructure devices."
    )
    parser.add_argument(
        "--user", help="Username for logging into the devices.", type=str
    )
    parser.add_argument(
        "--password", help="Password for logging into the devices.", type=str
    )
    parser.add_argument(
        "--enable", help="Enable password for the devices.", type=str, default=""
    )
    parser.add_argument(
        "--list",
        help="File containing the list of devices.",
        default="./switch-list.txt",
        type=str,
    )
    parser.add_argument(
        "--ping-list",
        help="List of devices to ping.",
        default="./ping-list.txt",
        type=str,
    )
    parser.add_argument(
        "--transfer-list",
        help=r"Tab-delimited file with <switch-ip>\t<source>\t<md5>\t<size>",
        type=str,
        default="./transfer-list.txt",
    )
    parser.add_argument(
        "--parallel", help="Number of threads to run in parallel.", default=80, type=int
    )
    parser.add_argument(
        "--delay", help="Global delay factor for timeouts.", type=int, default=10
    )
    parser.add_argument(
        "--driver", help="Napalm driver to use.", default="ios", type=str
    )
    parser.add_argument(
        "--transport",
        help="Transport protocol to use. (ssh/telnet)",
        default="ssh",
        type=str,
    )
    parser.add_argument(
        "function",
        help="""Function to run.
    fetch: fetch information from the list of devices.
    parse: parse output.json to hostname\tip\tmodel\timage\tversion\tboot-file\tfree-space in output.txt, and auth and connectivity failures.
    check-transport: check transport connectivity to the list of devices. (telnet or ssh)
    ping ip-to-ping.txt: ping a list of addresses, from a list of devices.
    transfer: verify files have been transferred, and copy files that have not been transferred. 
        **Note: 'transfer' currently should only be ran on devices that are not already running the latest firmware.
""",
        type=str,
        nargs=1,
    )
    args = vars(parser.parse_args())
    if "check-transport" in args["function"]:
        check_transport(args)
    elif "fetch" in args["function"]:
        fetch(args)
    elif "map-collect" in args["function"]:
        map_collect(args)
    elif "ping" in args["function"]:
        ping(args)
    elif "transfer" in args["function"]:
        transfer(args)


def check_transport(args):
    with open(args["list"], "r") as switches_file:
        switches = switches_file.read().splitlines()
    for switch in switches:
        if is_open(switch, 22):
            print(switch + "\t" + "ssh")
        elif is_open(switch, 23):
            print(switch + "\t" + "telnet")
        else:
            print(switch + "\t" + "Error")


def get_device(info):
    driver = get_network_driver(info["driver"])
    optional_args = {
        "global_delay_factor": info["delay"],
        "auth_timeout": int(info["delay"] * 10),
        "timeout": int(info["delay"] * 10),
        "banner_timeout": int(info["delay"] * 10),
    }
    if info["enable"] != "":
        optional_args["secret"] = info["enable"]
    if is_open(info["switch"], 22, timeout=int(info["delay"])):
        optional_args["transport"] = "ssh"
        device = driver(
            info["switch"], info["user"], info["password"], optional_args=optional_args
        )
    elif is_open(info["switch"], 23, timeout=int(info["delay"])):
        optional_args["transport"] = "telnet"
        device = driver(
            info["switch"], info["user"], info["password"], optional_args=optional_args
        )
    else:
        raise ConnectivityFailure(
            "SSH and Telnet connectivity failed to " + info["switch"]
        )
    print("Connecting to " + device.hostname)
    device.open()
    return device


def fetch(args):
    with open(args["list"], "r") as switches_file:
        switches = switches_file.read().splitlines()
    driver = get_network_driver(args["driver"])
    # Currently not parallel.
    output = dict()
    switch_list = list()
    for switch in switches:
        info = dict()
        info["driver"] = args["driver"]
        info["delay"] = args["delay"]
        info["switch"] = switch
        info["enable"] = args["enable"]
        info["user"] = args["user"]
        info["password"] = args["password"]
        switch_list.append(info)
    output = Parallel(n_jobs=args["parallel"], verbose=0, backend="threading")(
        map(delayed(fetch_helper), switch_list)
    )
    with open("output.json", "w") as f:
        f.write(json.dumps(output, indent=4))


def fetch_helper(info):
    try:
        device = get_device(info)
        parsed = dict()
        print("Running commands on " + device.hostname + "")
        commands = ["show version", "dir"]
        raw = device.cli(commands)
        parsed["raw"] = raw
        for command in commands:
            parsed[command] = parse.parse_output("cisco_ios", command, raw[command])
        print("Running 'get_facts' on " + device.hostname)
        parsed["facts"] = device.get_facts()
        # print("Grabbing running config from " + device.hostname)
        # parsed['config'] = device.cli(['show running-config'])
        # # get running image md5.
        # md5raw = device.cli(['verify /md5 flash:' + parsed['show version'][0]['running_image']])
        # parsed['md5'] = re.findall(r'.*= (.*)', md5raw[list(md5raw.keys())[0]])[0]
        image_name = re.match(r".*?\((.*?)\).*", parsed["facts"]["os_version"]).group(1)
        image_version = re.match(
            r".*Version (.*?),?\s.*", parsed["facts"]["os_version"]
        ).group(1)
        running_image_bin = parsed["show version"][0]["running_image"]
        free_space = parsed["dir"][0]["total_free"]
        print(
            parsed["facts"]["hostname"]
            + "\t"
            + device.hostname
            + "\t"
            + parsed["facts"]["model"]
            + "\t"
            + image_name
            + "\t"
            + image_version
            + "\t"
            + running_image_bin
            + "\t"
            + free_space
        )
        return {"device": device.hostname, "output": parsed}
    except ConnectivityFailure:
        print("SSH and Telnet connectivity failed to " + info["switch"])
        return {"device": info["switch"], "output": {"error": "Failed, Connectivity"}}
    except netmiko.exceptions.NetmikoAuthenticationException:
        print("Error authenticating to device " + device.hostname)
        print(traceback.format_exc())
        return {"device": device.hostname, "output": {"error": "Failed, Auth"}}
    except:
        print("Error with device " + device.hostname)
        print(traceback.format_exc())
        parsed["error"] = traceback.format_exc()
        return {"device": device.hostname, "output": parsed}


def transfer(args):
    with open(args["list"], "r") as switches_file:
        switches = switches_file.read().splitlines()
    output = dict()
    switch_list = list()
    for sw in switches:
        switch, version, file, md5 = sw.split("\t")
        info = dict()
        info["driver"] = args["driver"]
        info["delay"] = args["delay"]
        info["switch"] = switch
        info["enable"] = args["enable"]
        info["user"] = args["user"]
        info["password"] = args["password"]
        info["version"] = version
        info["file"] = file
        info["md5"] = md5
        switch_list.append(info)
    output = Parallel(n_jobs=args["parallel"], verbose=0, backend="threading")(
        map(delayed(fetch_helper), switch_list)
    )
    with open("output.json", "w") as f:
        f.write(json.dumps(output, indent=4))


def transfer_helper(info):
    try:
        device = get_device(info)
        parsed = dict()
        print("Running commands on " + device.hostname)
        commands = ["dir"]
        raw = device.cli(commands)
        parsed["raw"] = raw
        for command in commands:
            parsed[command] = parse.parse_output("cisco_ios", command, raw[command])
        if info["file"] in [a["name"] for a in parsed["dir"]]:
            md5raw = device.cli(
                ["verify /md5 flash:" + parsed["show version"][0]["running_image"]]
            )
            parsed["raw"]["verify"] = md5raw
            parsed["md5"] = re.findall(r".*= (.*)", md5raw[list(md5raw.keys())[0]])[0]
            if parsed["md5"] == info["md5"]:
                print(
                    "File "
                    + info["file"]
                    + " on device "
                    + device.hostname
                    + " has been verified."
                )
            else:
                needs_transfer = True
        else:
            needs_transfer = True
        if needs_transfer and info["confirm-copy"]:
            # check free space.
            free_space = parsed["dir"][0]["total_free"]
        elif not info["confirm-copy"]:
            print(
                "'confirm-copy' is needed alongside 'transfer' in order to copy the file. \nCopy for device "
                + device.hostname
                + " has been skipped."
            )

        return {"device": device.hostname, "output": parsed}
    except ConnectivityFailure:
        print("SSH and Telnet connectivity failed to " + info["switch"])
        return {"device": info["switch"], "output": {"error": "Failed, Connectivity"}}
    except netmiko.exceptions.NetmikoAuthenticationException:
        print("Error authenticating to device " + device.hostname)
        print(traceback.format_exc())
        return {"device": device.hostname, "output": {"error": "Failed, Auth"}}
    except:
        print("Error with device " + device.hostname)
        print(traceback.format_exc())
        parsed["error"] = traceback.format_exc()
        return {"device": device.hostname, "output": parsed}
    # check if file exists
    # if file exists, verify md5
    # if md5 doesn't match, or file doesn't exist verify free space
    # if free space, copy the file.


def map_collect(args):
    # Collect:
    #   traceroute to 10.70.148.121
    #   mac address-table
    #   lldp neighbors
    #   cdp neighbors
    pass


def ping(args):
    with open(args["ping_list"], "r") as switches_file:
        ping_list = switches_file.read().splitlines()
    with open(args["list"], "r") as switches_file:
        switches = switches_file.read().splitlines()
    driver = get_network_driver(args["driver"])
    # Currently not parallel.
    output = dict()
    switch_list = list()
    for switch in switches:
        info = dict()
        info["driver"] = args["driver"]
        info["delay"] = args["delay"]
        info["switch"] = switch
        info["enable"] = args["enable"]
        info["user"] = args["user"]
        info["password"] = args["password"]
        info["ping_list"] = ping_list
        switch_list.append(info)
    output = Parallel(n_jobs=args["parallel"], verbose=0, backend="threading")(
        map(delayed(ping_helper), switch_list)
    )
    with open("output.json", "w") as f:
        f.write(json.dumps(output, indent=4))


def ping_helper(info):
    driver = get_network_driver(info["driver"])
    optional_args = {
        "global_delay_factor": info["delay"],
        "auth_timeout": int(info["delay"] * 10),
        "timeout": int(info["delay"] * 10),
        "banner_timeout": int(info["delay"] * 10),
    }
    if info["enable"] != "":
        optional_args["secret"] = info["enable"]
    if is_open(info["switch"], 22, timeout=int(info["delay"])):
        optional_args["transport"] = "ssh"
        device = driver(
            info["switch"], info["user"], info["password"], optional_args=optional_args
        )
    elif is_open(info["switch"], 23, timeout=int(info["delay"])):
        optional_args["transport"] = "telnet"
        device = driver(
            info["switch"], info["user"], info["password"], optional_args=optional_args
        )
    else:
        print("Connectivity failed to " + info["switch"])
        return {"device": info["switch"], "output": {"error": "Failed, Connectivity"}}
    try:
        parsed = dict()
        print("Connecting to " + device.hostname)
        device.open()
        print("Running pings on " + device.hostname + "")
        parsed["pings"] = dict()
        for target in info["ping_list"]:
            print("Pinging " + target + " from " + device.hostname)
            parsed["pings"][target] = device.ping(target)
        return {"device": device.hostname, "output": parsed}
    except netmiko.exceptions.NetmikoAuthenticationException:
        print("Error authenticating to device " + device.hostname)
        print(traceback.format_exc())
        return {"device": device.hostname, "output": {"error": "Failed, Auth"}}
    except:
        print("Error with device " + device.hostname)
        print(traceback.format_exc())
        parsed["error"] = traceback.format_exc()
        return {"device": device.hostname, "output": parsed}


def is_open(ip, port, timeout=5):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    for retries in range(3):
        try:
            s.connect((ip, int(port)))
            s.shutdown(2)
            return True
        except:
            pass
    return False


if __name__ == "__main__":
    main()
