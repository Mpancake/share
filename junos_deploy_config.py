import os
import time
import questionary
from tqdm import tqdm
from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from jnpr.junos.exception import ConnectError, RpcTimeoutError, ConnectRefusedError, ConfigLoadError
from netmiko import ConnectHandler, NetMikoTimeoutException, NetMikoAuthenticationException
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Reduce verbosity of ncclient logs
ncclient_logger = logging.getLogger("ncclient")
ncclient_logger.setLevel(logging.WARNING)

def get_user_inputs():
    """
    Prompt the user for necessary inputs.

    Returns:
        tuple: A tuple containing the username, password, device list file path, debug option, and force CLI option.
    """
    answers = {
        'username': questionary.text('Enter your username:').ask(),
        'password': questionary.password('Enter your password:').ask(),
        'device_list': questionary.text('Enter the filename containing device IP addresses:').ask(),
        'debug': questionary.confirm('Enable debug output?', default=False).ask(),
        'force_cli': questionary.confirm('Force use of CLI for configuration deployment?', default=False).ask(),
    }
    return answers['username'], answers['password'], answers['device_list'], answers['debug'], answers['force_cli']

def connect_device(host, username, password, retries=2):
    """
    Connect to a Juniper device using Netconf.

    Args:
        host (str): The IP address or hostname of the device.
        username (str): The username for authentication.
        password (str): The password for authentication.
        retries (int, optional): Number of connection retry attempts. Defaults to 2.

    Returns:
        Device: A connected Junos device object or None if connection failed.
    """
    attempt = 0
    while attempt <= retries:
        try:
            device = Device(host=host, user=username, passwd=password)
            device.open()
            return device
        except ConnectRefusedError as err:
            logger.error(f"Failed to connect to device {host}: {err} (attempt {attempt + 1})")
            attempt += 1
            time.sleep(10)
        except ConnectTimeoutError as err:
            logger.error(f"Timeout error while connecting to device {host}: {err} (attempt {attempt + 1})")
            attempt += 1
            time.sleep(10)
    return None

def connect_device_ssh(host, username, password, retries=2):
    """
    Connect to a Juniper device using SSH with netmiko.

    Args:
        host (str): The IP address or hostname of the device.
        username (str): The username for authentication.
        password (str): The password for authentication.
        retries (int, optional): Number of connection retry attempts. Defaults to 2.

    Returns:
        netmiko.ConnectHandler: An SSH connection handler connected to the device or None if connection failed.
    """
    attempt = 0
    while attempt <= retries:
        try:
            net_connect = ConnectHandler(
                device_type='juniper',
                host=host,
                username=username,
                password=password,
                port=22
            )
            return net_connect
        except NetMikoTimeoutException as err:
            logger.error(f"SSH timeout to device {host}: {err} (attempt {attempt + 1})")
            attempt += 1
            time.sleep(10)
        except NetMikoAuthenticationException as err:
            logger.error(f"SSH authentication failed to device {host}: {err} (attempt {attempt + 1})")
            attempt += 1
            time.sleep(10)
        except Exception as err:
            logger.error(f"Failed to connect to device {host} via SSH: {err} (attempt {attempt + 1})")
            attempt += 1
            time.sleep(10)
    return None

def backup_rescue_configuration(device, use_cli=False, host=None, ssh=None):
    """
    Backup the current rescue configuration of the device.

    Args:
        device (Device or netmiko.ConnectHandler): The connected Junos device.
        use_cli (bool): Whether to use CLI commands.
        host (str): The hostname or IP address of the device.
        ssh (netmiko.ConnectHandler): SSH client for CLI fallback.

    Returns:
        bool: True if backup was successful, False otherwise.
    """
    try:
        if use_cli:
            logger.info(f"Backing up rescue configuration on {host} via CLI...")
            ssh.send_command('request system configuration rescue save', expect_string=r'>')
        else:
            logger.info(f"Backing up rescue configuration on {device.hostname}...")
            cu = Config(device)
            cu.rescue(action='save')
        logger.info("Rescue configuration backup complete.")
        return True
    except Exception as err:
        if use_cli:
            logger.error(f"Error backing up rescue configuration on {host}: {err}")
        else:
            logger.error(f"Error backing up rescue configuration on {device.hostname}: {err}")
        return False

def commit_pending_changes(device, use_cli=False, host=None, ssh=None, timeout=120):
    """
    Commit any pending changes on the device.

    Args:
        device (Device or netmiko.ConnectHandler): The connected Junos device.
        use_cli (bool): Whether to use CLI commands.
        host (str): The hostname or IP address of the device.
        ssh (netmiko.ConnectHandler): SSH client for CLI fallback.
        timeout (int, optional): Timeout for commit operation. Defaults to 120 seconds.

    Returns:
        bool: True if commit was successful, False otherwise.
    """
    try:
        if use_cli:
            logger.debug(f"Issuing 'edit' command on {host}")
            output = ssh.send_command('edit', expect_string=r'#', read_timeout=30)
            logger.debug(f"Output from 'edit': {output}")

            logger.debug(f"Issuing 'commit check' command on {host}")
            output = ssh.send_command('commit check', expect_string=r'#', read_timeout=60)
            logger.debug(f"Output from 'commit check': {output}")
            if 'configuration check succeeds' not in output:
                logger.error(f"Commit check failed on device {host}: {output}")
                return False

            logger.debug(f"Issuing second 'edit' command on {host}")
            ssh.send_command('edit', expect_string=r'#', read_timeout=30)
            logger.debug(f"Issuing 'commit and-quit' command on {host}")
            output = ssh.send_command('commit and-quit comment "MANUAL SCRIPT CLI FALLBACK COMMANDS"', expect_string=r'commit complete', read_timeout=120)
            logger.debug(f"Output from 'commit and-quit': {output}")
            if 'commit complete' not in output:
                logger.error(f"Commit failed on device {host}: {output}")
                return False

            logger.info(f"Pending changes committed on {host}")
        else:
            logger.debug(f"Using PyEZ to commit changes on {device.hostname}")
            cu = Config(device)
            if cu.commit_check():
                cu.commit(comment="Commit pending changes", timeout=timeout)
                logger.info(f"Pending changes committed on {device.hostname}")
        return True
    except Exception as err:
        if use_cli:
            logger.error(f"Failed to commit pending changes on device {host}: {err}")
        else:
            logger.error(f"Failed to commit pending changes on device {device.hostname}: {err}")
        return False


def apply_commands(device, commands, use_cli=False, host=None, ssh=None):
    """
    Apply a list of commands to the device.

    Args:
        device (Device or netmiko.ConnectHandler): The connected Junos device.
        commands (list): List of commands to apply.
        use_cli (bool): Whether to use CLI commands.
        host (str): The hostname or IP address of the device.
        ssh (netmiko.ConnectHandler): SSH client for CLI fallback.

    Returns:
        bool: True if commands were applied successfully, False otherwise.
    """
    try:
        if use_cli:
            logger.debug(f"Issuing 'edit' command on {host}")
            ssh.send_command('edit', expect_string=r'#', read_timeout=30)

            logger.debug(f"Applying configuration commands on {host}")
            ssh.send_config_set(commands, read_timeout=60)

            logger.debug(f"Issuing second 'edit' command on {host}")
            ssh.send_command('edit', expect_string=r'#', read_timeout=30)
            logger.debug(f"Issuing 'commit and-quit via CLI SSH FALLBACK' command on {host}")
            output = ssh.send_command('commit and-quit comment "MANUAL SCRIPT CLI FALLBACK COMMANDS"', expect_string=r'commit complete', read_timeout=120)
            logger.debug(f"Output from 'commit and-quit': {output}")
            if 'commit complete' not in output:
                logger.error(f"Commit failed on device {host}: {output}")
                return False

            logger.info(f"Commands applied on {host}")
        else:
            cu = Config(device)
            cu.load("\n".join(commands), format='set')
            cu.commit(comment='Apply configuration from file', timeout=120)
            logger.info(f"Commands applied on {device.hostname}")
        return True
    except ConfigLoadError as e:
        if use_cli:
            logger.warning(f"ConfigLoadError encountered on {host}: {e}. Proceeding with CLI fallback.")
            return apply_commands(device, commands, use_cli=True, host=host, ssh=ssh)
        else:
            logger.error(f"Failed to apply commands on device {device.hostname}: {e}")
            return False
    except Exception as err:
        if use_cli:
            logger.error(f"Failed to apply commands on device {host}: {err}")
        else:
            logger.error(f"Failed to apply commands on device {device.hostname}: {err}")
        return False

def read_config_file(config_file):
    """
    Read and return the configuration commands from the file, separated by type.

    Args:
        config_file (str): The path to the configuration file.

    Returns:
        tuple: A tuple containing lists of delete, set, and insert commands.
    """
    delete_commands = []
    set_commands = []
    insert_commands = []

    with open(config_file, 'r') as file:
        for line in file:
            line = line.strip()
            if line.startswith('delete'):
                delete_commands.append(line)
            elif line.startswith('set'):
                set_commands.append(line)
            elif line.startswith('insert'):
                insert_commands.append(line)

    return delete_commands, set_commands, insert_commands

def deploy_configuration(device, delete_commands, set_commands, insert_commands, use_cli=False, host=None, ssh=None):
    """
    Deploy the configuration commands to the device.

    Args:
        device (Device or netmiko.ConnectHandler): The connected Junos device.
        delete_commands (list): List of delete commands.
        set_commands (list): List of set commands.
        insert_commands (list): List of insert commands.
        use_cli (bool): Whether to use CLI commands.
        host (str): The hostname or IP address of the device.
        ssh (netmiko.ConnectHandler): SSH client for CLI fallback.

    Returns:
        bool: True if deployment was successful, False otherwise.
    """
    try:
        if use_cli:
            if delete_commands:
                logger.debug(f"Applying delete commands on {host}")
                if not apply_commands(device, delete_commands, use_cli=use_cli, host=host, ssh=ssh):
                    return False

            if set_commands:
                logger.debug(f"Applying set commands on {host}")
                if not apply_commands(device, set_commands, use_cli=use_cli, host=host, ssh=ssh):
                    return False

            if insert_commands:
                logger.debug(f"Applying insert commands on {host}")
                if not apply_commands(device, insert_commands, use_cli=use_cli, host=host, ssh=ssh):
                    return False
        else:
            if delete_commands:
                logger.debug(f"Applying delete commands on {device.hostname}")
                if not apply_commands(device, delete_commands):
                    return False

            if set_commands:
                logger.debug(f"Applying set commands on {device.hostname}")
                if not apply_commands(device, set_commands):
                    return False

            if insert_commands:
                logger.debug(f"Applying insert commands on {device.hostname}")
                if not apply_commands(device, insert_commands):
                    return False

        return True
    except Exception as err:
        logger.error(f"Failed to deploy configuration on device {host if use_cli else device.hostname}: {err}")
        return False

def main():
    username, password, device_list_file, debug, force_cli = get_user_inputs()

    if debug:
        logger.setLevel(logging.DEBUG)

    # Read the device list
    with open(device_list_file, 'r') as file:
        devices = [line.strip() for line in file if line.strip()]

    # Read the configuration commands
    delete_commands, set_commands, insert_commands = read_config_file('junos_deploy_config.txt')

    successful_nodes = []
    unsuccessful_nodes = []

    # Deploy configuration to each device
    for device_ip in tqdm(devices, desc="Overall Progress"):
        use_cli = force_cli  # Force CLI if the option is set by the user
        logger.info(f"Connecting to device {device_ip} using {'CLI' if use_cli else 'Netconf'}...")

        device = None
        ssh = None
        host = device_ip

        if not use_cli:
            device = connect_device(device_ip, username, password)
            if not device:
                logger.error(f"Failed to connect to device {device_ip} using Netconf. Falling back to CLI...")
                use_cli = True

        if use_cli:
            ssh = connect_device_ssh(device_ip, username, password)
            if not ssh:
                logger.error(f"Failed to connect to device {device_ip} using CLI.")
                unsuccessful_nodes.append(device_ip)
                continue
        else:
            host = device.hostname

        if not backup_rescue_configuration(device, use_cli=use_cli, host=host, ssh=ssh):
            unsuccessful_nodes.append(host)
            continue

        if not commit_pending_changes(device, use_cli=use_cli, host=host, ssh=ssh):
            unsuccessful_nodes.append(host)
            continue

        if not deploy_configuration(device, delete_commands, set_commands, insert_commands, use_cli=use_cli, host=host, ssh=ssh):
            unsuccessful_nodes.append(host)
            continue

        successful_nodes.append(host)
        logger.info(f"Configuration deployed on {host}")

    logger.info("Summary of configuration deployment:")
    logger.info(f"Successful nodes: {', '.join(successful_nodes) if successful_nodes else 'None'}")
    logger.info(f"Unsuccessful nodes: {', '.join(unsuccessful_nodes) if unsuccessful_nodes else 'None'}")

if __name__ == "__main__":
    main()
