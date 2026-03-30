#!/usr/bin/env python3

import meraki
import json
import sqlite3
import datetime
from pathlib import Path

read_me = '''
A Python 3 script to count the total unique client MAC addresses connected
to MR and CW access points for an organization during the last month.

Required Python modules:
    meraki 1.48.0 or higher

Usage:
clientcount_sdk.py

If you have only one Organization, it will count all clients automatically.
If you have multiple Organizations, it will ask you which org to run against.

Output:
Creates a CSV file in Documents/ClientCount/OrganizationName with client MAC
addresses and the networks they were found in.

API Key:
requires you to have your API key in env vars as 'MERAKI_DASHBOARD_API_KEY'

'''

MAX_CLIENT_TIMESPAN = 2592000  # 30 days in seconds

p = Path.home()
loc = p / 'Documents' / 'ClientCount'

dashboard = meraki.DashboardAPI(suppress_logging=True)


def base_folder():
    '''
    Check if the root folder exists and create it if not
    '''
    if not Path.is_dir(loc):
        Path.mkdir(loc)


def org_folder(org_name):
    '''
    Check if the organization folder exists, create if not
    '''
    loc2 = Path.joinpath(loc, org_name)
    if not Path.is_dir(loc2):
        Path.mkdir(loc2)


def get_orgs():
    '''
    Get a list of organizations the user has access to and return that list
    '''
    orgs = dashboard.organizations.getOrganizations()
    return orgs


def find_org(org_list):
    '''
    If only one organization exists, use that org_id
    If there are multiple organizations, ask the user which one to use
    '''
    if len(org_list) == 1:
        org_id = org_list[0]['id']
        org_name = org_list[0]['name']
    else:
        org_dict = {org['id']: org['name'] for org in org_list}
        org_id = input(
            f"Please type the Organization ID you want to count clients for"
            f"{json.dumps(org_dict, indent=4)}" "\n")
        org_name = org_dict.get(org_id)
    return org_id, org_name


def get_wireless_devices(org_id):
    '''
    Get all MR and CW (wireless) devices for an organization
    '''
    all_devices = dashboard.organizations.getOrganizationDevices(
        org_id, total_pages='all')

    # Filter for MR and CW devices
    wireless_devices = [device for device in all_devices
                        if device.get('model', '').startswith(('MR', 'CW'))]

    return wireless_devices


def get_networks(org_id):
    '''
    Get all networks for an organization
    '''
    net_list = dashboard.organizations.getOrganizationNetworks(
        org_id, total_pages='all')
    return net_list


def collect_clients(org_id, org_name, wireless_devices, networks):
    '''
    Collect all clients from MR and CW devices and deduplicate using SQLite
    '''
    print(f'INFO: Starting client collection for "{org_name}" at {datetime.datetime.now()}')

    # Create network ID to name mapping
    network_map = {net['id']: net['name'] for net in networks}

    # Create in-memory database for deduplication
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()

    cursor.execute('''
        CREATE TABLE clients (
            mac TEXT PRIMARY KEY,
            org_id TEXT,
            org_name TEXT,
            network_id TEXT,
            network_name TEXT,
            device_serial TEXT,
            device_name TEXT
        )
    ''')
    db.commit()

    total_devices = len(wireless_devices)
    processed_devices = 0

    print(f'INFO: Found {total_devices} wireless device(s)')

    # Get clients for each device
    for device in wireless_devices:
        serial = device['serial']
        device_name = device.get('name', serial)
        network_id = device.get('networkId', 'Unknown')
        network_name = network_map.get(network_id, 'Unknown')
        processed_devices += 1

        try:
            clients = dashboard.devices.getDeviceClients(
                serial,
                timespan=MAX_CLIENT_TIMESPAN
            )

            # Insert clients into database (PRIMARY KEY ensures deduplication)
            for client in clients:
                try:
                    cursor.execute('''
                        INSERT OR IGNORE INTO clients (mac, org_id, org_name, network_id, network_name, device_serial, device_name)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        client['mac'],
                        org_id,
                        org_name,
                        network_id,
                        network_name,
                        serial,
                        device_name
                    ))
                except KeyError:
                    # Skip clients without MAC address
                    continue

            if processed_devices % 10 == 0:
                print(f'INFO: Processed {processed_devices}/{total_devices} devices')

        except Exception as e:
            print(f'WARNING: Unable to fetch clients for device {serial}: {e}')
            continue

    db.commit()
    print(f'INFO: Client collection complete at {datetime.datetime.now()}')

    return db


def count_unique_clients(db):
    '''
    Count unique MAC addresses from the database
    '''
    cursor = db.cursor()
    cursor.execute('SELECT COUNT(DISTINCT mac) FROM clients')
    unique_count = cursor.fetchone()[0]
    return unique_count


def file_writer(db, org_name):
    '''
    Write client data to CSV file
    '''
    print('Writing client data to CSV file')

    cursor = db.cursor()
    cursor.execute('''
        SELECT mac, network_name, device_name, device_serial
        FROM clients
        ORDER BY network_name, mac
    ''')

    rows = cursor.fetchall()

    file = f'{loc}/{org_name}/client_count.csv'
    with open(file, mode='w') as f:
        f.write("Client MAC, Network Name, Device Name, Device Serial\n")
        for row in rows:
            f.write(f"{row[0]}, {row[1]}, {row[2]}, {row[3]}\n")

    print(f'Your file client_count.csv has been created in {loc}/{org_name}')


def main():
    print(read_me)

    # Create base folder
    base_folder()

    # Get organizations
    org_list = get_orgs()

    # Find/select organization
    org_id, org_name = find_org(org_list)

    # Create organization folder
    org_folder(org_name)

    print(f'\nINFO: Processing organization "{org_name}"')

    # Get networks
    networks = get_networks(org_id)

    # Get wireless devices (MR and CW)
    wireless_devices = get_wireless_devices(org_id)

    if not wireless_devices:
        print(f'WARNING: No Access Points found in organization "{org_name}"')
        return

    # Collect clients
    db = collect_clients(org_id, org_name, wireless_devices, networks)

    # Count unique clients
    unique_count = count_unique_clients(db)

    # Display results
    print(f'\nTotal unique client MAC addresses across all WLAN APs: {unique_count}\n')

    # Write to CSV file
    file_writer(db, org_name)

    db.close()


if __name__ == '__main__':
    main()
