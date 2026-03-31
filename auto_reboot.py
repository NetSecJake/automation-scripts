#!/usr/bin/env python3

readMe = """A Python 3 script to automatically reboot devices with a matching device tag on a weekly schedule.
The default tag matched is "auto-reboot". Tag devices in the Meraki dashboard with this device tag to
enable automatic reboots.

Script syntax, Windows:
    python auto_reboot.py [-o <org_name>] [-d <day_of_week>] [-t <time>] [-g <device_tag>]

Script syntax, Linux and Mac:
    python3 auto_reboot.py [-o <org_name>] [-d <day_of_week>] [-t <time>] [-g <device_tag>]

Optional parameters:
    -o <org_name>       The name of the organization to perform the reboots on. Use keyword "/all" instead of
                        an organization name to perform the operation for all organizations accessible by
                        your API key. This parameter can be omitted if your API key can only access one org
    -d <day_of_week>    Day of the week to perform the operation. Valid options: Monday, Tuesday, Wednesday,
                        Thursday, Friday, Saturday, Sunday. If omitted, default is Sunday
    -t <time>           Time to perform the operation. 24h format is recommended. If omitted, default is "00:00".
                        Note that time is relative to system time of the computer that runs this script
    -g <device_tag>     Devices that have the specified tag as a device tag will be rebooted. If omitted,
                        default is "auto-reboot"

Example, reboot all devices with tag "access-point" in organization Big Industries Inc every Sunday at 00:00:
    python auto_reboot.py -o "Big Industries Inc" -g access-point

API Key:
    Requires you to have your API key in environment variable MERAKI_DASHBOARD_API_KEY

Required Python 3 modules:
    meraki
    schedule

To install these Python 3 modules via pip you can use the following commands:
    pip install meraki
    pip install schedule

Depending on your operating system and Python environment, you may need to use commands
"python3" and "pip3" instead of "python" and "pip".
"""

import sys
import getopt
import time
import datetime
import schedule
import meraki

# Initialize Meraki Dashboard API
dashboard = meraki.DashboardAPI(suppress_logging=True) 
    


def log(text, filePath=None):
    logString = "%s -- %s" % (str(datetime.datetime.now())[:19], text)
    print(logString)
    if not filePath is None:
        try:
            with open(filePath, "a") as logFile:
                logFile.write("%s\n" % logString)
        except:
            log("ERROR: Unable to append to log file")


def killScript(reason=None):
    if reason is None:
        print(readMe)
        sys.exit()
    else:
        log("ERROR: %s" % reason)
        sys.exit()


JOB_ARGUMENTS = {"organizations": [], "tag": None}


def rebootDevices():
    log("Rebooting devices...")
    organizations = JOB_ARGUMENTS['organizations']
    tag = JOB_ARGUMENTS['tag']

    for org in organizations:
        try:
            inventory = dashboard.organizations.getOrganizationInventoryDevices(org['id'])
            for device in inventory:
                if (device.get('networkId') is not None) and tag in device.get('tags', []):
                    log(f"Rebooting device {device['serial']} ({device.get('name', 'Unknown')})")
                    dashboard.devices.rebootDevice(device['serial'])
        except meraki.APIError as e:
            log(f"ERROR: API error for org {org['name']}: {e}")
        except Exception as e:
            log(f"ERROR: Unexpected error for org {org['name']}: {e}")

    log("Process complete. Waiting for next cycle...")


def scheduleDayObject(day):
    mappings = {
        'monday': schedule.every().monday,
        'tuesday': schedule.every().tuesday,
        'wednesday': schedule.every().wednesday,
        'thursday': schedule.every().thursday,
        'friday': schedule.every().friday,
        'saturday': schedule.every().saturday,
        'sunday': schedule.every().sunday
    }

    lowerDay = str(day).lower()

    if lowerDay in mappings:
        return mappings[lowerDay]
    return None


def main(argv):
    arg_orgName = None
    arg_day = "Sunday"
    arg_time = "00:00"
    arg_tag = "auto-reboot"

    try:
        opts, args = getopt.getopt(argv, 'o:d:t:g:h:')
    except getopt.GetoptError:
        killScript()

    for opt, arg in opts:
        if opt == '-o':
            arg_orgName = str(arg)
        if opt == '-d':
            arg_day = str(arg)
        if opt == '-t':
            arg_time = str(arg)
        if opt == '-g':
            arg_tag = str(arg)
        if opt == '-h':
            killScript()

    try:
        allOrgs = dashboard.organizations.getOrganizations()
    except Exception as e:
        killScript(f"Unable to fetch organizations: {e}")

    organizations = []
    if arg_orgName is None:
        if len(allOrgs) == 1:
            organizations = allOrgs
        else:
            killScript("Organization name required for this API key")
    elif arg_orgName == "/all":
        organizations = allOrgs
    else:
        for org in allOrgs:
            if org["name"] == arg_orgName:
                organizations.append(org)
                break
    if len(organizations) == 0:
        killScript("No matching organizations")

    log("Reboot schedule configuration:\n------------\nDay:    %s\nTime:   %s\nTag:    %s\nOrganizations:" % (
        arg_day.capitalize(), arg_time, arg_tag))
    for org in organizations:
        print("%s (%s)" % (org['name'], org['id']))
    print("------------")

    dayObject = scheduleDayObject(arg_day)
    if dayObject is None:
        killScript("Invalid day-of-the-week argument")
    JOB_ARGUMENTS['organizations'] = organizations
    JOB_ARGUMENTS['tag'] = arg_tag
    dayObject.at(arg_time).do(rebootDevices)

    log("Starting scheduler...")
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main(sys.argv[1:])
