#!/usr/bin/python
# Nutanix Rest Api v3
# Python 2.7.9

from ansible.module_utils.basic import *
import base64
import logging
import urllib2
import json
import socket
import sys
import pprint
import time
import ssl
import os


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

class RestApi():

    def __init__(self, ip_addr, username, password):
        # Initialise the options.
        self.ip_addr = ip_addr
        self.username = username
        self.password = password
        self.rest_params_init()

    # Initialize REST API parameters
    def rest_params_init(self, sub_url="", method="",
                         body=None, content_type="application/json"):
        self.sub_url = sub_url
        self.body = body
        self.method = method
        self.content_type = content_type

    # Create a REST client session.
    def rest_call(self):
        base_url = 'https://%s:9440/api/nutanix/v3/%s' % (
            self.ip_addr, self.sub_url)
        if self.body and self.content_type == "application/json":
            self.body = json.dumps(self.body)
        request = urllib2.Request(base_url, data=self.body)
        base64string = base64.encodestring(
            '%s:%s' %
            (self.username, self.password)).replace(
            '\n', '')
        request.add_header("Authorization", "Basic %s" % base64string)

        request.add_header(
            'Content-Type',
            '%s; charset=utf-8' %
            self.content_type)
        request.get_method = lambda: self.method

        try:
            if sys.version_info >= (2, 7, 9):
                ssl_context = ssl._create_unverified_context()
                response = urllib2.urlopen(request, context=ssl_context)
            else:
                response = urllib2.urlopen(request)
            result = response.read()
            if result:
                result = json.loads(result)
            return response.code, result
        except urllib2.HTTPError as e:
            err_result = e.read()
            if err_result:
                try:
                    err_result = json.loads(err_result)
                except:
                    #print "Error: %s" % e
                    return "408", None
            return "408", err_result
        except Exception as e:
            #print "Error: %s" % e
            return "408", None

class ApiLibrary:
    def __init__(self):
        self.cluster_responses = {"200": "success", "201": "success", "202": "success", "400": "input_error",
                                  "401": "input_error", "403": "input_error", "408": "request_timeout",
                                  "409": "input_error", "404": "api_not_available", "501": "Internal Server Error"}
        pass

    # toparse : List to be parsed
    # lookfor : key for which parse is to be done
    def parse_list(self, toparse, lookfor):
        for data in toparse:
            if isinstance(data, dict):
                return data.get(lookfor)

    # Parse a complex dictionary.
    # result : dictionary to parse
    # meta_key : the key which has sub key for which parse is being done.
    # look_for: the key for which parse is to be done.
    def parse_result(self, result, meta_key, lookfor):
        uuid = None
        if result:
            for key in result:
                if key == meta_key:
                    if isinstance(result[key], list):
                        uuid = self.parse_list(result[key], lookfor)
                        return uuid
                    else:
                        if isinstance(result[key], dict):
                            return result[key].get(lookfor, None)
                        return result[key]
                elif isinstance(result[key], dict):
                    uuid = self.parse_result(result[key], meta_key, lookfor)
                    if uuid:
                        return uuid

        return uuid

    # Check the return status of API executed
    def check_api_status(self, status, result):
        if result:
            return self.parse_result(result, "status", "state")
        else:
            return None

    def print_failure_status(self, result):
        if result:
            status = result.get('status')
            if status:
                print '*' * 80
                state = self.parse_result(result, "status", "state")
                print state
                if state == "Error" or "ERROR":
                    print "Reason: ", status.get('reason')
                    print "Message: ", status.get("message")
                else:
                    print "Reason: ", result.get('reason')
                    print "Details: ", result.get('details')
                    print "Message: ", result.get("message")

    def __is_result_complete(self, status, result):
        if result and str(result.get('code')) == "404":
            return True
        if result and str(status) == "200" or "202":
            api_status = self.parse_result(result, "status", "state")
            #print api_status
            if api_status == "COMPLETE":
                return True
            elif api_status == "Error" or "ERROR":
                return None
        return False

    def track_completion_status(
            self, RestApi, status, result, get_api_status):
        start_time = time.clock()
        retry_count = 100
        wait_time = 3  # seconds
        uuid = None

        if result and str(status) == "200" or "202":
            uuid = self.parse_result(result, "metadata", "uuid")

        if self.__is_result_complete(status, result):
            return result, uuid
        else:
            api_status = self.parse_result(result, "status", "state")
            if uuid and api_status != "COMPLETE" and api_status != "Error":
                count = 0
                while count < retry_count:
                    count = count + 1
                    time.sleep(wait_time)
                    (status, result) = get_api_status(RestApi, uuid)
                    get_status = self.__is_result_complete(status, result)
                    # API status is COMPLETE
                    if get_status is True:
                        end_time = time.clock()
                        total_time_taken = end_time - start_time
                        #print "Total Time taken to complete:", total_time_taken
                        return result, uuid
                    # API status is Error
                    if get_status is None:
                        break

            return result, uuid
            #self.print_failure_status(result)
            #api_status = self.parse_result(result, "status", "state")
            #print "API status :", api_status
            #return None


def clone_vm_from_image(restApi, vm_name, image_uuid, subnet_uuid, cluster_uuid, memory, num_sockets, cores_per_socket,
                        power_state, cloud_config):
    # Get cloud-init config
    configfile = (open(cloud_config)).readlines()
    configreplace = [line.replace('vmname', vm_name) for line in configfile]
    cloudsettings = "".join(configreplace)
    config = base64.b64encode(cloudsettings).decode('ascii')
    # Create a configuration for Rest Api body
    body = {
      "spec": {
        "cluster_reference": {
          "kind": "cluster",
          "uuid": cluster_uuid
        },
        "resources": {
          "nic_list": [
            {
              "subnet_reference": {
                "kind": "subnet",
                "uuid": subnet_uuid
              }
            }
          ],
          "power_state": power_state,
          "num_vcpus_per_socket": int(cores_per_socket),
          "num_sockets": int(num_sockets),
          "memory_size_mib": int(memory),
          "guest_customization": {
            "cloud_init": {
              "user_data": config
            }
          },
          "disk_list": [
            {
              "data_source_reference": {
                "kind": "image",
                "uuid": image_uuid
              },
              "device_properties": {
                "disk_address": {
                  "device_index": 0,
                  "adapter_type": "SCSI"
                },
                "device_type": "DISK"
              }
            }
          ]
        },
        "name": vm_name
      },
      "api_version": "3.0",
      "metadata": {
            "categories": {},
            "kind": "vm"
      }
    }
    # Initialize setings of Rest Api
    restApi.rest_params_init(sub_url="vms", method="POST", body=body)
    # Call Rest Api
    (status, result) = restApi.rest_call()
    # Return result
    return status, result


def get_image(restApi, image_name):
    custom_filter = "%s%s" % ("name==", image_name)
    body = {
        "filter": custom_filter,
        "kind": "image"
    }
    restApi.rest_params_init(sub_url="images/list", method="POST", body=body)
    (status, result) = restApi.rest_call()
    #image_uuid = "".join([image['metadata']['uuid'] for image in result['entities']
    #                      if image['status']['name'] == image_name])
    #result = {'status': status, 'uuid': image_uuid.encode('ascii')}
    #return result
    return status, result


def get_network(restApi, vm_subnet):
    # Doesn't work with filtering
    body = {"kind": "subnet"}
    restApi.rest_params_init(sub_url="subnets/list", method="POST", body=body)
    (status, result) = restApi.rest_call()
    #subnet_uuid = "".join([subnet['metadata']['uuid'] for subnet in result['entities']
    #                      if subnet['status']['name'] == vm_subnet])
    #result = {'status': status, 'uuid': subnet_uuid.encode('ascii')}
    #return result
    return status, result


def get_cluster(restApi, cluster_name):
    # Works only with UUID filter
    body = {"kind": "cluster"}
    restApi.rest_params_init(sub_url="clusters/list", method="POST", body=body)
    (status, result) = restApi.rest_call()
    #cluster_uuid = "".join([cluster['metadata']['uuid'] for cluster in result['entities']
    #                       if cluster['status']['name'] == cluster_name])
    #result = {'status': status, 'uuid': cluster_uuid.encode('ascii')}
    #return result
    return status, result


# Get a VM with particular UUID.
def get_vm_by_uuid(restApi, vm_uuid):
    sub_url = 'vms/%s' % vm_uuid
    restApi.rest_params_init(sub_url='vms/%s' % vm_uuid, method="GET")
    (status, result) = restApi.rest_call()
    return status, result

def api_response_(status, result_list, origin_name):
    api_library = ApiLibrary()
    api_response = api_library.cluster_responses

    item_kind = api_library.parse_result(result_list, "metadata", "kind")
    if api_response[str(status)] == "success":
        items = result_list.get('entities')
        #print('%s UUID List' % item_kind)
        for item in items:
            item_name = api_library.parse_result(item, "status", "name")
            if item_name == origin_name:
                item_uuid = api_library.parse_result(item, "metadata", "uuid")
                #print('%s uuid: %s' % (item_kind, item_uuid))
                return item_uuid
    else:
        ### Need add exception to stop processing
        #print "Failed to get clusters list."
        #api_library.print_failure_status(result_list)
        return None


def extract_value(dict_in, search_key):
    result = []
    for key, value in dict_in.iteritems():
        if isinstance(value, dict):   # If key itself is a dictionary
            return extract_value(value, search_key)
        elif isinstance(value, list):   # If key itself is a list
            for item in value:
                return extract_value(item, search_key)
        elif isinstance(value, unicode) and key == search_key:
            # Write to dict_out
            result.append(value.encode())
    return result


def main():
    retry_count = 100
    # define the available arguments/parameters that a user can pass to the module
    module_args = dict(
        name=dict(type='str', required=True),
        image=dict(type='str', required=True),
        network=dict(type='str', required=True),
        cluster=dict(type='str', required=True),
        memory=dict(type='int', required=True),
        cores_per_socket=dict(type='int', required=True),
        numvcpu=dict(type='int', required=True),
        state=dict(type='str', required=True),
        user=dict(type='str', required=True),
        password=dict(type='str', required=True),
        cvm_address=dict(type='str', required=True),
        cloud_config=dict(type='str', required=True)
    )
    # seed the result dict in the object
    # we primarily care about changed and state
    # change is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result_output = dict(
        changed=False,
        UUID='',
        IP_address='',
        hostname='',
        message=''
    )
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)
    rest_api = RestApi(module.params['cvm_address'], module.params['user'], module.params['password'])

    # Get cluster UUID
    (status, result) = get_cluster(rest_api, module.params['cluster'])
    cluster_uuid = api_response_(status, result, module.params['cluster'])

    # Get image UUID
    (status, result) = get_image(rest_api, module.params['image'])
    image_uuid = api_response_(status, result, module.params['image'])

    # Get subnet UUID
    (status, result) = get_network(rest_api, module.params['network'])
    subnet_uuid = api_response_(status, result, module.params['network'])

    (status, result) = clone_vm_from_image(restApi=rest_api, vm_name=module.params['name'], image_uuid=image_uuid,
                                           subnet_uuid=subnet_uuid, cluster_uuid=cluster_uuid,
                                           memory=module.params['memory'], num_sockets=module.params['numvcpu'],
                                           cores_per_socket=module.params['cores_per_socket'],
                                           power_state=module.params['state'],
                                           cloud_config=module.params['cloud_config'])
    api_library = ApiLibrary()
    api_response = api_library.cluster_responses
    if api_response[str(status)] == "success":
        (result, item_uuid) = api_library.track_completion_status(rest_api, status, result, get_vm_by_uuid)
        exe_status = result['status']['state'].encode()
        if exe_status.lower() != 'error':
            count = 0
            while count < retry_count:
                count += 1
                (status, result) = get_vm_by_uuid(restApi=rest_api, vm_uuid=item_uuid)
                vm_ip = extract_value(result, 'ip')
                if vm_ip:
                    result_output['IP_address'] = "".join(vm_ip)
                    result_output['hostname'] = module.params['name']
                    result_output['changed'] = True
                    result_output['UUID'] = item_uuid
                    result_output['message'] = "Operation succeed"
                    module.exit_json(**result_output)
                    break
                time.sleep(3)
        else:
            output = extract_value(result, 'message')
            result_output['message'] = output
            module.fail_json(msg='You requested this to fail', **result_output)
    else:
        result_output['message'] = api_response[str(status)]
        module.fail_json(msg='You requested this to fail', **result_output)


if __name__ == '__main__':
    main()
