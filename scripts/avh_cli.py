#!/usr/bin/env python3

'''
Copyright 2021 Arm Ltd

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
'''

import argparse
import sys
import os
import subprocess
import json
import logging
import platform


# AWS ORTA-TEST connection details
# TODO will eventually change to public AMI
# version 0.3.0
ImgId="ami-030e410551d9b5fa5"

InstType="t3a.medium"

# Set verbosity level
verbosity = logging.INFO
# [debugging] Verbosity settings
level = { 10: "DEBUG",  20: "INFO",  30: "WARNING",  40: "ERROR" }
logging.basicConfig(format='[%(levelname)s]\t%(message)s', level = verbosity)
logging.debug("Verbosity level is set to " + level[verbosity])

# No colors for Windows
if platform.system() == "Windows" : 
    green=""
    orange=""
    red=""
    nc=""
else:
    green="\033[0;32m"
    orange="\033[0;33m"
    red="\033[0;31m"
    nc="\033[0m"


def start_orta(profile, key, region, initfile):
    global ImgId, InstType

    if status_orta(profile, region, False)[0] > 0 :
        print(orange + "One or more ORTA instances are already running." + nc)
        confirm = input("Please confirm to launch a new instance [Y/n]: ")
        if confirm != "Y":
            print("Cancelling... No instance will be started.")
            sys.exit(1)

    print("Starting ORTA instance...")

    cmd = "aws ec2 run-instances --profile {} --image-id {} --instance-type {} --key-name {} --region {}".format(
            profile, ImgId, InstType, key, region)

    if initfile != None :
        cmd = cmd + " --user-data file://{}".format(initfile.name)

    logging.debug("Command is: {}".format(cmd))

    try:
        out = subprocess.check_output(cmd, shell=True).decode("utf-8")
    except subprocess.CalledProcessError:
        logging.error(red + "Running the start command failed." + nc)

    outd = json.loads(out)
    for instance in outd['Instances']:
        print("Launched Instance ID {}".format(instance['InstanceId']))

    return

def status_orta(profile, region, printv):
    global ImgId

    n_instances = 0
    arr_inst = []

    cmd = 'aws ec2 describe-instances --query "Reservations[*].Instances[*].[State.Name, ImageId, PublicIpAddress, InstanceId]" --profile {} --region {} --output json'.format(profile, region)

    logging.debug("Command is: {}".format(cmd))

    try:
        out = subprocess.check_output(cmd, shell=True).decode("utf-8")
    except subprocess.CalledProcessError:
        logging.error(red + "Running the status command failed." + nc)
        sys.exit(1)

    outd = json.loads(out)
    for reservation in range(len(outd)):
        for instance in range(len(outd[reservation])):
            if outd[reservation][instance][1] == ImgId :
                if outd[reservation][instance][0] == 'running' :
                    n_instances += 1
                arr_inst.append([outd[reservation][instance][3], outd[reservation][instance][2], outd[reservation][instance][0]])

    if printv == True :
        print("| Instance ID\t\t| Public IP\t| Status\t|")
        print('=========================================================')
        for i in arr_inst :
            if i[2] == 'running' :
                print("| {}\t| {}\t| ".format(i[0], i[1]) + green + "RUNNING" + nc + "\t|")
            elif i[2] == 'shutting-down' :
                print("| {}\t| {}\t| ".format(i[0], i[1]) + red + "SHUTTING DOWN" + nc + "\t|")
            elif i[2] == 'pending' :
                print("| {}\t| {}\t| ".format(i[0], i[1]) + orange + "{}".format(i[2]) + nc + "\t|")
            else :
                print("| {}\t| {}\t\t| {}\t|".format(i[0], i[1], i[2]))

    return n_instances, arr_inst


def stop_orta(profile, region):
    [n, arr] = status_orta(profile, region, False)

    if n == 0 :
        logging.error(red + "No ORTA instance is running." + nc)
        sys.exit(1)
    else:
        if n > 1:
            print(orange + "Many instances found!" + nc)

        for i in arr :
            if i[2] == 'running' :
                print("Running instance ID {} found (public IP {})".format(i[0], i[1]))

        instanceid = input("The instance will be terminated and all data will be lost. Please enter the instance ID to stop it (leave empty to cancel): ")

        if(instanceid == ""):
            print("Cancelling... No instance will be stopped.")
        else:
            print(orange + "Stopping ORTA instance ID {}...".format(instanceid) + nc)

            cmd = "aws ec2 terminate-instances --profile {} --instance-ids {} --region {}".format(
                    profile, instanceid, region)

            try:
                out = subprocess.check_output(cmd, shell=True).decode("utf-8")
            except subprocess.CalledProcessError:
                logging.error(red + "Running the stop command failed." + nc)

            logging.debug("Command is: {}".format(cmd))
            return


# Command options
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ORTA command-line interface for AWS. Starts (launches) a single ORTA AMI instance and stops (terminates) it.")
    parser.add_argument("-p", dest="profile", metavar="NAME", action="store", type=str, help=("Name of the profile configuration (default is 'default')"), default="default")
    parser.add_argument("-k", dest="key", metavar="KEY", action="store", type=str, help=("Name of the AWS key. If not specified, a key will be created"))
    parser.add_argument("-r", dest="region", metavar="REGION", action="store", type=str, help=("Name of the AWS region (default is 'us-east-1')"), default="us-east-1")
    parser.add_argument("-i", dest="cloudinit", metavar="FILE", action="store", type=argparse.FileType('r'), help=("Location of cloud-init file for instance configuration"))
    parser.add_argument("command", metavar="start|status|stop", action="store", type=str, help=("Start, status or stop command"))
    args = parser.parse_args()

    # Check AWS CLI is installed
    try:
        awscli_version_f = subprocess.check_output("aws --version", shell=True).decode("utf-8").split()[0].split("/")[1]
    except subprocess.CalledProcessError:
        logging.error(red + "AWS CLI not found." + nc)
        sys.exit(1)

    # AWS CLI version check
    awscli_version_m = float(awscli_version_f.split(".")[0] + "." + awscli_version_f.split(".")[1])
    if awscli_version_m < 2.2 :
        logging.warning(red + "AWS CLI version is: {}. Minimum required is 2.2".format(awscli_version_m) + nc)

    # Profile check
    try:
        awscli_version_f = subprocess.check_output(
                "aws configure list --profile {}".format(args.profile), 
                shell=True)
    except subprocess.CalledProcessError:
        logging.error(red  + "Profile {} not found.".format(args.profile) + nc)
        sys.exit(1)

    if args.profile == "default" :
        logging.info("Selected profile: {}".format(args.profile))


    # Start / Stop / Status commands
    if args.command.lower() == "start" :
        # Key check
        if args.key == None:
            args.key = "orta_user"
            if os.path.isfile(os.path.join(os.path.expanduser('~'),'.ssh/orta_user.pem')) == False :
                logging.info(red + "No key specified and orta_user key not found, creating 'orta_user' key..." + nc)

                cmd = "aws ec2 create-key-pair --key-name orta_user --profile {} --region {}".format(
                            args.profile, args.region)
                try:
                    out = subprocess.check_output(cmd, shell=True).decode("utf-8")
                except subprocess.CalledProcessError:
                    logging.error(red + "Creating a key failed." + nc)
                    sys.exit(1)

                outd = json.loads(out)
                key_file = open(os.path.join(os.path.expanduser('~'),'.ssh/orta_user.pem'), 'x')
                try:
                    key_file.write(outd["KeyMaterial"])
                except:
                    logging.error(red + "Saving key in {}.ssh failed.".format(os.path.expanduser('~') + os.path.sep) + nc)
                    sys.exit(1)

                key_file.close()

                # Set permissions
                if platform.system() == "Linux" :
                    os.system('chmod 600 ~/.ssh/orta_user.pem')

                logging.info(orange + "Key has been saved as {}.ssh".format(os.path.expanduser('~') + os.path.sep) + os.path.sep + "orta_user.pem." + nc)
            else:
                logging.info(orange + "Using 'orta_user' key in {}.ssh ...".format(os.path.expanduser('~') + os.path.sep) + nc)

        start_orta(args.profile, args.key, args.region, args.cloudinit)

    elif args.command.lower() == "status" :
        status_orta(args.profile, args.region, True)

    elif args.command.lower() == "stop" :
        stop_orta(args.profile, args.region)

    else :
        logging.error(red + "Unknown command." + nc)

    sys.exit(0)

