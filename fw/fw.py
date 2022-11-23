from napalm import get_network_driver
import re
from ntc_templates import parse
import argparse
import socket
import json
from joblib import Parallel, delayed
import traceback
import netmiko.exceptions
from time import sleep
from datetime import datetime


class ConnectivityFailure(Exception):
    pass


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


def fetch(args):
    with open(args["list"], "r") as switches_file:
        switches = switches_file.read().splitlines()
    driver = get_network_driver(args["driver"])
    # Currently not parallel.
    output = dict()
    switch_list = list()
    for switch in switches:
        # args contains driver, delay, enable, user and password that is passed as 'info' to the helper function.
        info = args
        info["switch"] = switch
        switch_list.append(info)
    output = Parallel(n_jobs=args["parallel"], verbose=0, backend="threading")(
        map(delayed(fetch_helper), switch_list)
    )
    with open(args["output"], "w") as f:
        f.write(json.dumps(output, indent=4))
    parse_output(args)


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
        print("Information collection for " + device.hostname + " complete.")
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
        try:
            device.close()
        except:
            pass
        return {"device": device.hostname, "output": parsed}


def parse_output(args):
    with open(args["output"], "r") as f:
        data = json.loads(f.read())
    for e in data:
        if "error" not in e["output"]:
            parsed = e["output"]
            image_name = re.match(
                r".*?\((.*?)\).*", parsed["facts"]["os_version"]
            ).group(1)
            image_version = re.match(
                r".*Version (.*?),?\s.*", parsed["facts"]["os_version"]
            ).group(1)
            running_image_bin = parsed["show version"][0]["running_image"]
            free_space = parsed["dir"][0]["total_free"]
            print(
                parsed["facts"]["hostname"]
                + "\t"
                + e["device"]
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
                + "\n"
            )
        else:
            print(
                parsed["facts"]["hostname"]
                + "\t"
                + e["device"]
                + "\t"
                + "\t"
                + "\t"
                + "\t"
                + "\t"
                + "\t"
                + str(e["output"]["error"]).replace("\n", r"\n")
                + "\n"
            )


def transfer(args):
    with open(args["list"], "r") as switches_file:
        switches = switches_file.read().splitlines()
    output = dict()
    switch_list = list()
    for sw in switches:
        switch, version, file, size, md5 = sw.split("\t")
        # args contains driver, delay, enable, user, password, and confirm_transfer that is passed as 'info' to the helper function.
        info = args
        info["switch"] = switch
        info["version"] = version
        info["file"] = file
        info["size"] = size
        info["md5"] = md5
        switch_list.append(info)
    output = Parallel(n_jobs=args["parallel"], verbose=0, backend="threading")(
        map(delayed(transfer_helper), switch_list)
    )
    with open(args["output"], "w") as f:
        f.write(json.dumps(output, indent=4))


def transfer_helper(info):
    try:
        device = get_device(info)
        parsed = dict()
        print("Running commands on " + device.hostname)
        commands = ["show version", "dir"]
        raw = device.cli(commands)
        parsed["raw"] = raw
        for command in commands:
            parsed[command] = parse.parse_output("cisco_ios", command, raw[command])
        print("Running 'get_facts' on " + device.hostname)
        parsed["facts"] = device.get_facts()
        image_version = re.match(
            r".*Version (.*?),?\s.*", parsed["facts"]["os_version"]
        ).group(1)
        # Make sure the current version is not already running.
        if image_version == info["version"]:
            parsed["ready"] = False
            parsed["transferred"] = False
            parsed["up-to-date"] = True
            parsed["notes"] = "Already up to date."
            return {"device": device.hostname, "output": parsed}
        # Check if the file already exists.
        try:
            if re.match(".*/(.*)", info["file"]).group(1) in [
                a["name"] for a in parsed["dir"]
            ]:
                parsed["raw"]["verify"], device, info = verify_helper(device, info)
                parsed["md5"] = re.findall(r".*= (.*)", parsed["raw"]["verify"])[0]
                if parsed["md5"] == info["md5"]:
                    print(
                        "File "
                        + info["file"]
                        + " on device "
                        + device.hostname
                        + " has been verified. Ready for upgrade."
                    )
                    parsed["ready"] = True
                    parsed["transferred"] = False
                    parsed["up-to-date"] = False
                    return {"device": device.hostname, "output": parsed}
        except:
            # defaults to re-copying the file if the file check or md5 causes issues.
            print("Error checking for existing file on " + device.hostname)
            print("Current file list = " + str(parsed["dir"]))
            print("Current file = " + info["file"])
            print(traceback.format_exc())
        # Make sure there is enough free space.
        free_space = parsed["dir"][0]["total_free"]
        if int(info["size"]) >= int(free_space):
            print("Not enough free space on device " + device.hostname)
            parsed["ready"] = False
            parsed["transferred"] = False
            parsed["up-to-date"] = False
            parsed["notes"] = "Not enough free space."
            return {"device": device.hostname, "output": parsed}
        # Make sure 'confirm-copy' was entered - not a dry run.
        if not info["confirm_transfer"]:
            print(
                "'confirm-copy' is needed alongside 'transfer' in order to copy the file. \nCopy for device "
                + device.hostname
                + " has been skipped."
            )
            parsed["ready"] = False
            parsed["transferred"] = False
            parsed["up-to-date"] = False
            parsed["notes"] = "Dry-run only."
            return {"device": device.hostname, "output": parsed}
        # Perform the copy. This requires a separate netmiko connection,
        # as most switches are configured for an interactive session.
        else:
            # file_copy_status = device.cli(['copy ' + info['file'] + ' flash:\n\n\n'])
            # info = {'driver': 'ios', 'delay': 5, 'enable': '', 'switch': '192.168.1.254', 'transport': 'ssh', 'user': 'admin', 'password': 'password', 'file': 'ftp://192.168.1.143/c2960x-universalk9-mz.152-7.E7.bin'}
            hostname = device._netmiko_device.find_prompt()
            if hostname[-1:] == ">":
                device._netmiko_device.enable()
                hostname = device._netmiko_device.find_prompt()
            print("Beginning file copy on " + device.hostname)
            start_time = datetime.now()
            copy_progress = device._netmiko_device.send_command_timing(
                "copy " + info["file"] + " flash:"
            )
            possible_prompts = {r"Address or name of remote host \[.*\]?": '\n',
                                r"Source username \[.*\]\? ": 'anonymous\n',
                                r"Source filename \[.*\]\?": '\n',
                                r".*Destination filename \[.*\]\?": '\n',
                                r"Do you want to over write\? \[.*\]": 'confirm\n',
                                r"Password:": '\n'}
            copying = True
            last_print = ''
            while copying:
                copy_progress += device._netmiko_device.read_channel()
                for match, command in possible_prompts.items():
                    # only check the last line. Avoids regex multiline headaches.
                    check = copy_progress.splitlines()[-1] 
                    if re.match(match, check):
                        device._netmiko_device.write_channel(command)
                if hostname in copy_progress:
                    copying = False
                else:
                    if 'scp' in info["file"]:
                        progress_modifier = 10000
                    else:
                        progress_modifier = 256000
                    percent_complete = (copy_progress.count("!") * progress_modifier) / int(
                        info["size"]
                    )
                    if percent_complete > 0.01:
                        eta = ((datetime.now() - start_time) / percent_complete) - (
                            datetime.now() - start_time
                        )
                        print(
                            "Copy ~"
                            + "{:.0%}".format(percent_complete)
                            + " complete on "
                            + device.hostname
                            + " Estimated Time Remaining: "
                            + str(eta)
                        )
                sleep(5)
            print(
                "File copy for "
                + device.hostname
                + " completed in "
                + str(start_time - datetime.now())
            )
            # Verify the md5 of the copied file.
            parsed["raw"]["verify"], device, info = verify_helper(device, info)
            parsed["md5"] = re.findall(r".*= (.*)", parsed["raw"]["verify"])[0]
            if parsed["md5"] == info["md5"]:
                parsed["ready"] = True
                parsed["transferred"] = True
                parsed["up-to-date"] = False
                parsed["notes"] = ""
                print(
                    "File "
                    + info["file"]
                    + " on device "
                    + device.hostname
                    + " has been verified. Ready for upgrade."
                )
            else:
                parsed["ready"] = False
                parsed["transferred"] = True
                parsed["up-to-date"] = False
                parsed["notes"] = "MD5 verification failed after transfer."
                print(
                    "File "
                    + info["file"]
                    + " on device "
                    + device.hostname
                    + " validation failed. md5: "
                    + parsed["md5"]
                    + " does not match the expected value: "
                    + info["md5"]
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
        try:
            device.close()
        except:
            pass
        return {"device": device.hostname, "output": parsed}


def verify_helper(device, info):
    print("Beginning file verification on " + device.hostname)
    hostname = device._netmiko_device.find_prompt()
    if hostname[-1:] == ">":
        device._netmiko_device.enable()
        hostname = device._netmiko_device.find_prompt()
    filename = "flash:/" + re.match(".*/(.*)", info["file"]).group(1)
    start_time = datetime.now()
    verify_progress = device._netmiko_device.send_command(
        "verify /md5 " + filename, expect_string=""
    )
    verifying = True
    while verifying:
        verify_progress += device._netmiko_device.read_channel()
        if (
            "Done!" in verify_progress
            and len(re.findall(r".*= (.*)", verify_progress)) > 0
        ):
            verifying = False
        else:
            percent_complete = (verify_progress.count(".") * 4096) / int(info["size"])
            if percent_complete > 0.01:
                eta = ((datetime.now() - start_time) / percent_complete) - (
                    datetime.now() - start_time
                )
                print(
                    "Verification ~"
                    + "{:.0%}".format(percent_complete)
                    + " complete on "
                    + device.hostname
                    + " Estimated Time Remaining: "
                    + str(eta)
                )
        sleep(5)
    return verify_progress, device, info


def main():
    parser = argparse.ArgumentParser(
        description="Utility to help with firmware upgrades of network infrastructure devices."
    )
    parser.add_argument(
        "--user", help="Username for logging into the devices.", type=str, default=""
    )
    parser.add_argument(
        "--password",
        help="Password for logging into the devices.",
        type=str,
        default="",
    )
    parser.add_argument(
        "--enable", help="Enable password for the devices.", type=str, default=""
    )
    parser.add_argument(
        "--list",
        help="File containing the list of devices, of list of devices and files to transfer. Default: ./switch-list.txt",
        default="./switch-list.txt",
        type=str,
    )
    parser.add_argument(
        "--parallel",
        help="Number of threads to run in parallel. Default: 80",
        default=80,
        type=int,
    )
    parser.add_argument(
        "--delay",
        help="Global delay factor for timeouts. Default: 10",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--driver", help="Napalm driver to use. Default: ios", default="ios", type=str
    )
    parser.add_argument(
        "--confirm-transfer",
        help="Disable dry-run mode, and allow copying of files.",
        default=False,
        action="store_true",
    )
    parser.add_argument(
        "--output",
        help="File to save the output data to. Default 'output.json'",
        type=str,
        default="output.json",
    )
    parser.add_argument(
        "function",
        help="""Function to run.
    fetch: fetch information from the list of devices.
    parse: parse output.json (--output) to hostname, ip, model, image, version, boot-file, and free-space in output.txt.
    check-transport: check transport connectivity to the list of devices. (telnet or ssh)
    transfer: verify files have been transferred, and copy files that have not been transferred. 
""",
        type=str,
        nargs=1,
    )
    args = vars(parser.parse_args())
    if "check-transport" in args["function"]:
        check_transport(args)
    elif "fetch" in args["function"]:
        fetch(args)
    # elif "parse" in args["function"]:
    #     parse(args)
    elif "transfer" in args["function"]:
        transfer(args)


if __name__ == "__main__":
    main()
