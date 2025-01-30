# Juniper JUNOS Configuration Deployment Script

This Python script connects to a list of Juniper JUNOS devices via SSH and deploys configurations specified in a text-based configuration file using Junos PyEZ. It also backs up the current configuration using the `rescue save` command before deploying the new configuration. The script provides a summary of successful and unsuccessful deployments, similar to Ansible playbook output.

---

## Table of Contents
1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Configuration File](#configuration-file)
4. [Usage](#usage)
5. [Script Workflow](#script-workflow)
6. [Output](#output)
7. [Troubleshooting](#troubleshooting)
8. [License](#license)

---

## Requirements

### Python 3
Ensure Python 3 is installed on your system. You can check by running:
```bash
python --version
````

### Required Python Libraries
The script uses the following libraries:

junos-eznc: For Junos PyEZ operations.
netmiko: For SSH fallback operations.
questionary: For interactive user input.
tqdm: For progress bars.

### Install the required libraries using pip:
```bash
pip install -r requirements.txt
````
Configuration File
Create a text file named junos_deploy_config.txt in the same directory as the script. This file should contain the CLI-based commands for configuring Junos devices. For example:

```bash
delete firewall family inet filter protectRE
insert firewall family inet filter protectRE term VRRP before term mBFD
set system services netconf ssh connection-limit 32
````
## Device List File
Create a text file containing the IP addresses of the Juniper devices, one per line. For example:

```bash
192.168.1.1
192.168.1.2
192.168.1.3
````
## Installation
Clone or download the script to your working directory.

### Install the required Python libraries:

```bash
pip install -r requirements.txt
````
Ensure the configuration file (junos_deploy_config.txt) and device list file are in the same directory as the script.

## Usage
### Run the script:

```bash
python junos_deploy_config.py

? Enter your username: tsaidamer
? Enter your password: *********
? Enter the filename containing device IP addresses: devices.txt
? Enable debug output? Yes
? Force use of CLI for configuration deployment? Yes
````
### Provide the following inputs when prompted:

Username: Your SSH username for the Juniper devices.
Password: Your SSH password for the Juniper devices.
Device List File: The filename containing the IP addresses of the devices (e.g., devices.txt).
Debug Output: Enable or disable debug output (optional).
Force CLI: Force the script to use CLI instead of Netconf (optional).

### The script will:

Key Features
Automatic Netconf → CLI fallback
Configuration backup via rescue save
Atomic configuration commits
Progress bars with tqdm
Color-coded success/failure summaries

### Script Workflow
User Input: The script prompts for username, password, device list file, debug mode, and CLI fallback preference.
Device Connection: The script attempts to connect to each device using Netconf. If Netconf fails, it falls back to SSH (CLI).
Backup Configuration: The script backs up the current configuration using the rescue save command.
Deploy Configuration: The script applies the configuration commands from junos_deploy_config.txt.
Commit Changes: The script commits the changes on the device.

### Summary: The script provides a summary of successful and unsuccessful deployments.

####Connection
Attempt Netconf → Fallback to CLI if:

Connection refused
RPC timeout
Netconf not enabled

#### Backup

```bash
request system configuration rescue save
````
#### Validation

```bash
commit check
````
#### Deployment
Applies commands in order:

```bash
1. delete → 2. insert → 3. set
Commit
````

```bash
commit and-quit comment "Automated deployment"
````

#### Output
The script outputs the following:

Progress bars for each device.
Logs of configuration deployment steps.
A summary of successful and unsuccessful deployments.

#### Example output:

```bash
Overall Progress: 100%|████████████████████████████████████████| 3/3 [00:30<00:00, 10.00s/it]
INFO: Configuration deployed on 192.168.1.1
INFO: Configuration deployed on 192.168.1.2
ERROR: Failed to deploy configuration on 192.168.1.3
INFO: Summary of configuration deployment:
INFO: Successful nodes: 192.168.1.1, 192.168.1.2
INFO: Unsuccessful nodes: 192.168.1.3
````

## Troubleshooting

### Connection Issues:

Ensure the devices are reachable and SSH/Netconf is enabled.
Verify the username and password are correct.
Check firewall rules if the connection is refused.

### Configuration Errors:

Ensure the commands in junos_deploy_config.txt are valid for the target devices.
Check the logs for specific error messages.

### Debug Mode:

Enable debug mode to get detailed logs for troubleshooting.
