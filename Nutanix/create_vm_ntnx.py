#!/usr/local/bin/pythonw
# Nutanix Rest Api v3
# Python 2.7.9

import urllib2
import base64
import json
import socket
import sys
import pprint
import time
import ssl
import argparse

# socket timeout in seconds
TIMEOUT = 30
socket.setdefaulttimeout(TIMEOUT)
pp = pprint.PrettyPrinter(indent=4)

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
                    print "Error: %s" % e
                    return "408", None
            return "408", err_result
        except Exception as e:
            print "Error: %s" % e
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
            print api_status
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
            return uuid
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
                        print "Total Time taken to complete:", total_time_taken
                        return uuid
                    # API status is Error
                    if get_status is None:
                        break

            self.print_failure_status(result)
            api_status = self.parse_result(result, "status", "state")
            print "API status :", api_status
            return None


def clone_vm_from_image(restApi, vm_name, image_uuid, subnet_uuid, cluster_uuid, memory, num_sockets, vm_vcpu,
                        power_state):
    # Get cloud-init config
    configfile = (open("template-cfg.yml")).readlines()
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
          "num_vcpus_per_socket": int(vm_vcpu),
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
        print "Failed to get clusters list."
        api_library.print_failure_status(result_list)
        return


def main(task, vm_name, image_name, vm_cluster, vm_network, vm_memory, vm_num_sockets, vm_vcpu, vm_power_state, user, password,
         cvm_address):

    #rest_api = RestApi("ntnx-548b1f14-a-cvm.local", "admin", "1qaz@WSX3edc")
    rest_api = RestApi(cvm_address, user, password)

    # Get cluster UUID
    (status, result) = get_cluster(rest_api, vm_cluster)
    cluster_uuid = api_response_(status, result, vm_cluster)

    # Get image UUID
    (status, result) = get_image(rest_api, image_name)
    image_uuid = api_response_(status, result, image_name)

    # Get subnet UUID
    (status, result) = get_network(rest_api, vm_network)
    subnet_uuid = api_response_(status, result, vm_network)

    (status, result) = clone_vm_from_image(restApi=rest_api, vm_name=vm_name, image_uuid=image_uuid, subnet_uuid=subnet_uuid,
                        cluster_uuid=cluster_uuid, memory=vm_memory, num_sockets=vm_num_sockets, vm_vcpu=vm_vcpu,
                        power_state=vm_power_state)
    api_library = ApiLibrary()
    api_response = api_library.cluster_responses
    if api_response[str(status)] == "success":
        item_uuid = api_library.parse_result(result, "metadata", "uuid")
        print(item_uuid)
        return item_uuid
    else:
        print "Failed to get clusters list."
        api_library.print_failure_status(result)
        return

if __name__ == '__main__':
    # Fetch required parameters
    """parser = argparse.ArgumentParser(description='Create a VM on Nutanix.')
    parser.add_argument('-name', type=str, dest='vm_name', required=True, help='Virtual machine name')
    parser.add_argument('-image', type=str, dest='image', required=True, help='Image name')
    parser.add_argument('-network', type=str, dest='network', required=True, help='Network name')
    parser.add_argument('-cluster', type=str, dest='cluster', required=True, help='Nutanix cluster name')
    parser.add_argument('-memory', type=int, dest='memory', required=True, help='Memory size in MB')
    parser.add_argument('-vcpu', type=int, dest='vcpu', required=True, help='Amount of vCPU')
    parser.add_argument('-numvcpu', type=int, dest='numvcpu', required=True, help='Amount of sockets')
    parser.add_argument('-state', type=str, dest='state', required=True, help='VM power state')
    parser.add_argument('-user', type=str, dest='userNTNX', required=True,
                        help='User with permission create VM on Nutanix cluster')
    parser.add_argument('-password', type=str, dest='passNTNX', required=True, help='Password of user')
    parser.add_argument('-cvm_address', type=str, dest='cvm_address', required=True, help='IP or FQDN of Nutanix cluster')
    args = parser.parse_args()"""
    #./create_vm_ntnx.py -name 'ansible-client10' -image 'Centos7-cloudInit' -cluster 'NTNX-lab' -network 'vlan0' -memory 1024 -numvcpu 1 -vcpu 1 -state 'ON' -user 'admin' -password '1qaz@WSX3edc' -cvm_address 'ntnx-548b1f14-a-cvm.local'

    # Temporal variable
    vm_name = "ansible-client10"
    image_name = "Centos7-cloudInit"
    vm_network = "vlan0"
    vm_cluster = "NTNX-lab"
    vm_memory = 1024
    vm_num_sockets = 1
    vm_vcpu = 1
    vm_power_state = "ON"
    user = 'admin'
    password = "1qaz@WSX3edc"
    cvm_address = 'ntnx-548b1f14-a-cvm.local'
    main('clone', vm_name=vm_name, image_name=image_name, vm_cluster=vm_cluster, vm_network=vm_network,
         vm_memory=vm_memory, vm_num_sockets=vm_num_sockets, vm_vcpu=vm_vcpu, vm_power_state=vm_power_state,
         cvm_address=cvm_address, user=user, password=password)
    ###


    #main('clone', vm_name=args.vm_name, image_name=args.image, vm_cluster=args.cluster, vm_network=args.network,
    #     vm_memory=args.memory, vm_num_sockets=args.numvcpu, vm_vcpu=args.vcpu, vm_power_state=args.state,
    #     cvm_address=args.cvm_address, user=args.userNTNX, password=args.passNTNX)


