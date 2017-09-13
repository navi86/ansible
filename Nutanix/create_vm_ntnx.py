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
        pass

    # Parse a list
    # list to parse
    # key for which parse is to be done
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
                        if type(result[key]) == dict:
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
                if state == "kError":
                    print "Reason: ", status.get('reason')
                    print "Message: ", status.get("message")
                else:
                    print "Reason: ", result.get('reason')
                    print "Details: ", result.get('details')
                    print "Message: ", result.get("message")

    def __is_result_complete(self, status, result):
        if result and str(result.get('code')) == "404":
            return True
        if result and str(status) == "200":
            api_status = self.parse_result(result, "status", "state")
            if api_status == "kComplete":
                return True
            elif api_status == "kError":
                return None
        return False

    def track_completion_status(
            self, RestApi, status, result, get_api_status):
        retry_count = 5
        wait_time = 2  # seconds
        uuid = None

        if result and str(status) == "200":
            uuid = self.parse_result(result, "metadata", "uuid")

        if self.__is_result_complete(status, result):
            return uuid
        else:
            api_status = self.parse_result(result, "status", "state")
            if uuid and api_status != "kComplete" and api_status != "kError":
                count = 0
                while count < retry_count:
                    count = count + 1
                    time.sleep(wait_time)
                    (status, result) = get_api_status(RestApi, uuid)
                    get_status = self.__is_result_complete(status, result)
                    # API status is kComplete
                    if get_status is True:
                        return uuid
                    # API status is Error
                    if get_status is None:
                        break

            self.print_failure_status(result)
            api_status = self.parse_result(result, "status", "state")
            print "API status :", api_status
            return None


    def track_deletion_status(self, RestApi, uuid, get_api_status):
        count = 0
        api_status = ""
        status = 0
        result = None
        while count < 3:
            count = count + 1
            time.sleep(5)
            (status, result) = get_api_status(RestApi, uuid)
            if result:
                if str(status) == "200":
                    api_status = self.parse_result(result, "status", "state")
                else:
                    api_status = result.get('status', None)
            if api_status == "failure":
                return True
        if not str(status) == "200":
            self.print_failure_status(result)
            return False
        else:
            if api_status == "kComplete":
                return True
            elif api_status == "failure":
                self.print_failure_status(result)
                return False
            elif api_status == "kError":
                print "Reason:", self.parse_result(result, "status", "reason")
                print "Message:", self.parse_result(result, "status", "message")
                return False
            else:
                print "Timed Out"
                print result
                return False


def create_vm(restApi, vm_name, network_uuid, cluster_uuid, memory, num_sockets,vcpu,power_state):
    body = {
        "spec": {
            "cluster_reference": {
                "kind": "cluster",
                "uuid": cluster_uuid,
            },
            "resources": {
                "num_vcpus_per_socket": int(vcpu),
                "nic_list": [
                    {
                        "subnet_reference": {
                            "kind": "subnet",
                            "uuid": network_uuid
                        }
                    }
                ],
                "memory_size_mib": int(memory),
                "power_state": power_state,
                "num_sockets": int(num_sockets)
            },
            "name": vm_name
        },
        "api_version": "3.0",
        "metadata": {
            "kind": "vm",
            }
    }

    restApi.rest_params_init(sub_url="vms", method="POST", body=body)
    (status, result) = restApi.rest_call()
    return status, result


def clone_vm_from_image(restApi, vm_name, image_name,subnet_name, cluster_name, memory, num_sockets,vcpu,power_state):
    # Get image UUID
    image_uuid = get_image(RestApi, image_name)
    # Get subnet UUID
    subnet_uuid = get_network(RestApi, subnet_name)
    # Get cluster UUID
    cluster_uuid = get_cluster(RestApi, cluster_name)
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
          "num_vcpus_per_socket": int(vcpu),
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
                "uuid": image_uuid,
                "name": image_name
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
    image_uuid = [image['metadata']['uuid'] for image in result['entities'] if image['status']['name'] == image_name]
    return status, image_uuid


def get_network(restApi, vm_subnet):
    # Doesn't work with filtering
    body = {"kind": "subnet"}
    restApi.rest_params_init(sub_url="subnets/list", method="POST", body=body)
    (status, result) = restApi.rest_call()
    subnet_uuid =[subnet['metadata']['uuid'] for subnet in result['entities'] if subnet['status']['name'] == vm_subnet]
    return status, subnet_uuid


def get_cluster(restApi, cluster_name):
    # Works only with UUID filter
    body = {"kind": "cluster"}
    restApi.rest_params_init(sub_url="clusters/list", method="POST", body=body)
    (status, result) = restApi.rest_call()
    cluster_uuid =[cluster['metadata']['uuid'] for cluster in result['entities'] if cluster['status']['name'] == cluster_name]
    return status, cluster_uuid


# Get a VM with particular UUID.
def get_vm_by_uuid(restApi, vm_uuid):
    sub_url = 'vms/%s' % vm_uuid
    restApi.rest_params_init(sub_url='vms/%s' % vm_uuid, method="GET")
    (status, result) = restApi.rest_call()
    return status, result



if __name__ == '__main__':

    RestApiconnection = RestApi("ntnx-548b1f14-a-cvm.local","admin",
                                "1qaz@WSX3edc")


    vm_name="ansible-client10"
    image_name="Centos7-cloudInit"
    vm_network="vlan0"
    vm_cluster="NTNX-lab"
    vm_memory=1024
    vm_num_sockets=1
    vm_vcpu=1
    vm_power_state="ON"

#print(clone_vm_from_image(RestApi=RestApiconnection, vm_name="ansible-client10",image_name="Centos7-cloudInit",
#                    network_uuid="88ba1a7c-5989-43a8-831f-e6355bb2b6d9",
#                    cluster_uuid="0005558c-536f-7adc-2348-001fc69c242b", memory=1024,
#                    num_sockets=1, vcpu=1, power_state="ON"))


