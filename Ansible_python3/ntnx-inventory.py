#!/usr/bin/python
# Nutanix Rest Api v3
# Python 3.6.3

import argparse
import json
import os
import pprint
import requests
import socket
import sys
from time import time
import urllib3
import yaml

# socket timeout in seconds
TIMEOUT = 30
socket.setdefaulttimeout(TIMEOUT)
pp = pprint.PrettyPrinter(indent=4)

DOCUMENTATION = '''
---
module: creat_vm_ntnx

short_description: This is  module for creation VM on Nutanix cluster

version_added: "1.0"

description:
    - "This is  module for creation VM on Nutanix cluster"

options:
    name:
        description:
            - This is the name of VM
        required: true
    image:
        description:
            - Name of the source image to deploy from
        required: true
    network:
        description:
            - Subnet name for new VM
        required: true
    cluster:
        description:
            - The name of the cluster to create the VM in.
        required: true
    memory:
        description:
            - Amount memory of VM.
        required: true
    cores_per_socket:
        description:
            - Amount cores per socket of VM.
        required: true
    numvcpu:
        description:
            - Amount cores of VM.
        required: true
    state:
        description:
            - Indicate desired state of the vm.
        required: true
    user:
        description:
            - Username to connect to Nutanix as.
        required: true
    password:
        description:
            - Password of the user to connect to Nutanix as.
        required: true
    cvm_address:
        description:
            - The hostname or IP address of the Nutanix CVM the module will connect to, to create VM.
        required: true
    cloud_config:
        description:
            - Cloud config file for customization VM.
        required: true

author:
    - Ivan Krylov (krylov.ivan86@gmail.com)
'''

EXAMPLES = '''
    create_vm_ntnx:
      name: 'test-vm'
      image: 'Centos7-image'
      network: 'vlan0'
      cluster: 'lab-test'
      memory: 512
      cores_per_socket: 1
      numvcpu: 1
      state: 'ON'
      user: 'admin'
      password: 'password'
      cvm_address: 'ntnx-abcd-a-cvm.local'
      cloud_config: 'cloud-config.yml'
'''

RETURN = '''
original_message:
    description: The original name param that was passed in
    type: str
message:
    description: The output message that the sample module generates
'''

class RestAPI(object):
    def __init__(self, ntnx_address, ntnx_username, ntnxt_password, ntnx_port, ntnx_verify_SSL):
        # Initialise the options.
        self.ntnx_address = ntnx_address
        self.ntnx_username = ntnx_username
        self.ntnxt_password = ntnxt_password
        self.ntnx_port = ntnx_port
        self.ntnx_verify_SSL = ntnx_verify_SSL
        self.rest_params_init()
        urllib3.disable_warnings()  # Disabling insecure warning of connection

    # Initialize REST API parameters
    def rest_params_init(self, sub_url='', method='', body=None, content_type='application/json'):
        self.sub_url = sub_url
        self.body = body
        self.method = method
        self.content_type = content_type

    # Create a REST client session.
    def rest_call(self):
        base_url = 'https://%s:%s/api/nutanix/v3/%s' % (self.ntnx_address, self.ntnx_port, self.sub_url)
        if self.body and self.content_type == "application/json":
            self.body = json.dumps(self.body)
        headers = {'Content-type': 'application/json', 'charset': 'utf-8'}
        request = requests.request(method=self.method, url=base_url, auth=(self.ntnx_username, self.ntnxt_password),
                                   data=self.body, headers=headers, verify=self.ntnx_verify_SSL)
        result = request.text
        if result:
            result = json.loads(result)
        return request.status_code, result


class Inventory(object):

    def _empty_inventory(self):
        return {"_meta": {"hostvars": {}}}

    def __init__(self):
        global config
        nutanix_mode = os.environ.get('NUTANIX_MODE')
        # Read settings and parse CLI arguments
        self.parse_cli_args()
        config = self.read_settings()
        #self.read_settings()

        # Build
        # Inventory grouped by instance IDs, tags
        # self.inventory()
        self.inventory = self._empty_inventory()

        # Cache
        if self.args.refresh_cache:
            self.do_api_calls_update_cache()
        elif not self.is_cache_valid():
            self.do_api_calls_update_cache()

        # Data to print
        if self.args.host:
            data_to_print = self.get_host_info()

        elif self.args.list:
            # Display list of instances for inventory
            if self.inventory == self._empty_inventory():
                data_to_print = self.get_inventory_from_cache()
            else:
                data_to_print = self.json_format_dict(self.inventory, True)
        print(data_to_print)

    def parse_cli_args(self):
        parser = argparse.ArgumentParser(description='Produce an Ansible Inventory file based on Nutanix')
        parser.add_argument('--list', action='store_true', default=True,
                            help='List instances by IP address (default: True)')
        parser.add_argument('--host', action='store',
                            help='Get all the variables about a specific instance')
        parser.add_argument('--refresh-cache', action='store_true', default=False,
                            help='Force refresh of cache by making API requests to Nutanix'
                                 ' (default: False - use cache files)')
        parser.add_argument('--readable', action='store_true',
                            help='Print result in readable format')

        self.args = parser.parse_args()

    def read_settings(self):
        ''' Retrieve settings from nutanix.yml '''

        nutanix_default_yml_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), 'nutanix.yml')

        nutanix_yml_path = os.path.expanduser(
            os.path.expandvars(
                os.environ.get('NUTANIX_YML_PATH', nutanix_default_yml_path)))

        try:
            with open(nutanix_yml_path) as nutanix_yml_file:
                config = yaml.safe_load(nutanix_yml_file)
        except IOError:
            print('Could not find nutanix.yml file at {}'
                  .format(nutanix_yml_path))
            sys.exit(1)
        # Configure nested groups instead of flat namespace.
        #if config.has_option('ec2', 'nested_groups'):
        settings = config.get('settings')
        try:
            settings = config.get('settings')
            try:
                self.nested_groups = settings['nested_groups']
            except KeyError:
                # Specified default value
                self.nested_groups = True
        except TypeError:
            # Specified default value
            self.nested_groups = True

        group_by_options = [
            'group_by_vm_id',
            'group_by_vm_state'
        ]
        for option in group_by_options:
            try:
                group_options = config.get('grouping')
                try:
                    setattr(self, option, group_options['group_by_vm_id'])
                except KeyError:
                    setattr(self, option, True)
                try:
                    setattr(self, option, group_options['group_by_vm_type'])
                except KeyError:
                    setattr(self, option, True)
                try:
                    setattr(self, option, group_options['group_by_vm_state'])
                except KeyError:
                    setattr(self, option, True)
                try:
                    setattr(self, option, group_options['group_by_platform'])
                except KeyError:
                    setattr(self, option, True)
            except TypeError:
                print('Could not load caching settings from nutanix.yml.')
                sys.exit(1)

        # Cache related
        try:
            cache_settings = config.get('caching')
            try:
                self.cache_max_age = cache_settings['cache_max_age']
            except KeyError:
                print('A caching time must be set, even if set to 0.')
                sys.exit(1)
            try:
                cache_name = 'ansible-ntnx'
                self.cache_path = cache_settings['cache_path']
                self.cache_path_cache = os.path.join(self.cache_path, cache_name)
            except KeyError:
                print('A path must be set for cached inventory files.')
                sys.exit(1)
            try:
                self.cache_base_name = cache_settings['cache_base_name']
            except KeyError:
                print('A base name must be set for cached inventory files.')
                sys.exit(1)

        except TypeError:
            print('Could not load caching settings from nutanix.yml.')
            sys.exit(1)

        return config

    def is_cache_valid(self):
        ''' Determines if the cache files have expired, or if it is still valid '''

        if os.path.isfile(self.cache_path_cache):
            mod_time = os.path.getmtime(self.cache_path_cache)
            current_time = time()
            if (mod_time + self.cache_max_age) > current_time:
                    return True

        return False

    def do_api_calls_update_cache(self):
        ''' Do API calls to each region, and save data in cache files '''
        try:
            cluster_list = config.get('clusters')
            for cluster in cluster_list:
                cluster_info = cluster_list[cluster]
                # Get Nutanix address
                try:
                    self.ntnx_address = cluster_info['address']
                except KeyError:
                    print('There is no address for cluster in the nutanix.yml configuration file.')
                    sys.exit(1)
                # Get Nutanix user
                try:
                    self.ntnx_user = cluster_info['username']
                except KeyError:
                    print('User must be configured in the nutanix.yml configuration file.')
                    sys.exit(1)
                # Get Nutanix password
                try:
                    self.ntnx_password = cluster_info['password']
                except KeyError:
                    print('Password must be configured in the nutanix.yml configuration file.')
                    sys.exit(1)
                if 'port' in cluster_info:
                    self.ntnx_port = cluster_info['port']
                else:
                    self.ntnx_port = 9440
                if 'verify_ssl' in cluster_info:
                    self.ntnx_verify_SSL = cluster_info['verify_ssl']
                else:
                    self.ntnx_verify_SSL = True

                self.restApi = RestAPI(self.ntnx_address, self.ntnx_user, self.ntnx_password, self.ntnx_port,
                                       self.ntnx_verify_SSL)
                self.inventory.update(self.create_inventory())
                #if self.args.readable:
                #    print(json.dumps(self.inventory, sort_keys=True, indent=2))
                #else:
                #    print(self.inventory)
            return None
            '''return {
                'all': {
                    'hosts': ["192.168.88.235"],
                    'vars': {},
                },
                '_meta': {
                    'hostvars': {
                        "192.168.88.235": {
                            'ansible_ssh_user': 'root',
                        }
                    },
                },
                'pi': ["192.168.88.235"]
            }'''
        except TypeError:
            print('No cluster found in the nutanix.yml configuration file.')
            sys.exit(1)

        self.write_to_cache(self.inventory, self.cache_path_cache)
        print('nothing')

    def create_inventory(self):
        status, vms_list = self.get_vms()
        if status == 200:
            for entity in vms_list['entities']:
                # Set the inventory name
                hostname = entity['status']['name']

                # Inventory: Group by vm id
                if self.group_by_vm_id:
                    vm_uuid = entity['metadata']['uuid']
                    self.inventory[vm_uuid] = [hostname]
                    if self.nested_groups:
                        self.push_group(self.inventory, 'instances', vm_uuid)

                # Inventory: Group by vm state
                if self.group_by_vm_state:
                    #state_name = self.to_safe('instance_state_' + entity['status']['resources']['power_state'])
                    state_name = entity['status']['resources']['power_state']
                    self.push(self.inventory, state_name, hostname)
                    if self.nested_groups:
                        self.push_group(self.inventory, 'instance_states', state_name)
                IP_addresses = (self.extract_value(entity['status'], 'ip'))
                if '_meta' not in self.inventory:
                    self.inventory['_meta'] = {'hostvars': {}}
                for IP_address in IP_addresses:
                    if IP_address not in self.inventory['_meta']['hostvars'] and IP_address is not []:
                        self.inventory['_meta']['hostvars'][hostname] = {}
                        self.inventory["_meta"]["hostvars"][hostname]['ansible_host'] = IP_addresses
            return self.inventory
        else:
            print('Could not get information from the cluster')

    def get_vms(self):
        # custom_filter = "%s%s" % ("name!=", "NTNX-548b1f14-A-CVM")
        body = {
            "kind": "vm"
        }
        self.restApi.rest_params_init(sub_url="vms/list", method="POST", body=body)
        (status, result) = self.restApi.rest_call()
        return status, result

    def extract_value(self, dict_in, search_key):
        result = []
        for key, value in dict_in.items():
            if isinstance(value, str) and key == search_key:
                result.append(value)
            if isinstance(value, dict):  # If key itself is a dictionary
                result.extend(self.extract_value(value, search_key))
            elif isinstance(value, list):  # If key itself is a list
                for item in value:
                    result.extend(self.extract_value(item, search_key))
        return result

    def write_to_cache(self, data, filename):
        ''' Writes data in JSON format to a file '''

        json_data = self.json_format_dict(data, True)
        with open(filename, 'w') as f:
            f.write(json_data)

    def json_format_dict(self, data, pretty=False):
        ''' Converts a dict to a JSON object and dumps it as a formatted
        string '''

        if pretty:
            return json.dumps(data, sort_keys=True, indent=2)
        else:
            return json.dumps(data)

    def get_inventory_from_cache(self):
        ''' Reads the inventory from the cache file and returns it as a JSON
        object '''

        with open(self.cache_path_cache, 'r') as f:
            json_inventory = f.read()
            return json_inventory

    def push(self, my_dict, key, element):
        ''' Push an element onto an array that may not have been defined in
        the dict '''
        group_info = my_dict.setdefault(key, [])
        if isinstance(group_info, dict):
            host_list = group_info.setdefault('hosts', [])
            host_list.append(element)
        else:
            group_info.append(element)

    def push_group(self, my_dict, key, element):
        ''' Push a group as a child of another group. '''
        parent_group = my_dict.setdefault(key, {})
        if not isinstance(parent_group, dict):
            parent_group = my_dict[key] = {'hosts': parent_group}
        child_groups = parent_group.setdefault('children', [])
        if element not in child_groups:
            child_groups.append(element)

if __name__ == '__main__':
    # Run the script
    Inventory()
