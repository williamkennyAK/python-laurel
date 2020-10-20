# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import dimond
import requests


API_TIMEOUT = 5

class LaurelException(Exception):
    pass

def authenticate(username, password):
    """Authenticate with the API and get a token."""
    API_AUTH = "https://api2.xlink.cn/v2/user_auth"
    auth_data = {'corp_id': "1007d2ad150c4000", 'email': username,
                 'password': password}
    r = requests.post(API_AUTH, json=auth_data, timeout=API_TIMEOUT)
    try:
        return (r.json()['access_token'], r.json()['user_id'])
    except KeyError:
        raise(LaurelException('API authentication failed'))


def get_devices(auth_token, user):
    """Get a list of devices for a particular user."""
    API_DEVICES = "https://api2.xlink.cn/v2/user/{user}/subscribe/devices"
    headers = {'Access-Token': auth_token}
    r = requests.get(API_DEVICES.format(user=user), headers=headers,
                     timeout=API_TIMEOUT)
    return r.json()

def get_properties(auth_token, product_id, device_id):
    """Get properties for a single device."""
    API_DEVICE_INFO = "https://api2.xlink.cn/v2/product/{product_id}/device/{device_id}/property"
    headers = {'Access-Token': auth_token}
    r = requests.get(API_DEVICE_INFO.format(product_id=product_id, device_id=device_id), headers=headers, timeout=API_TIMEOUT)
    return r.json()

    def _get_user(auth_token, user):
        """Get information about the user."""
        API_USER = "https://api2.xlink.cn/v2/user/{user}"
        headers = {'Access-Token': auth_token}
        r = requests.get(API_USER.format(user=user), headers=headers, timeout=API_TIMEOUT)
        return r.json()


    (auth_token, user) = _authenticate(username, password)
    user_info = _get_user(auth_token, user)
    devices = _get_devices(auth_token, user)
    for device in devices:
        product_id = device['product_id']
        device_id = device['id']
        device_info = _get_device(auth_token, product_id, device_id)

def callback(link, data):
    if data[7] != 0xdc:
        return
    responses = data[10:18]
    for i in (0, 4):
        response = responses[i:i+4]
        for device in link.devices:
            if device.id == response[0]:
                device.brightness = response[2]
                if device.brightness >= 128:
                  device.brightness = device.brightness - 128
                  device.red = int(((response[3] & 0xe0) >> 5) * 255 / 7)
                  device.green = int(((response[3] & 0x1c) >> 2) * 255 / 7)
                  device.blue = int((response[3] & 0x3) * 255 / 3)
                  device.rgb = True
                else:
                  device.temperature = response[3]
                  device.rgb = False
                if device.callback is not None:
                    device.callback(device.cbargs)

class laurel:
    def __init__(self, user, password, use_mesh=1):
        (self.auth, self.userid) = authenticate(user, password)
        self.devices = []
        self.networks = []
        self.mesh=use_mesh
        mesh_networks = get_devices(self.auth, self.userid)
        for mesh in mesh_networks:
            network = None
            devices = []
            properties = get_properties(self.auth, mesh['product_id'],
                                        mesh['id'])
            if 'error' in properties:
                continue
            else:
                for bulb in properties['bulbsArray']:
                    id = int(bulb['deviceID'][-3:])
                    mac = [bulb['mac'][i:i+2] for i in range(0, 12, 2)]
                    mac = "%s:%s:%s:%s:%s:%s" % (mac[5], mac[4], mac[3], mac[2], mac[1], mac[0])
                    if network is None:
                        network = laurel_mesh(mesh['mac'], mesh['access_key'], self.mesh)
                    device = laurel_device(network, {'name': bulb['displayName'], 'mac': mac, 'id': id, 'type': bulb['deviceType']})
                    network.devices.append(device)
                    self.devices.append(device)
            self.networks.append(network)

class laurel_mesh:
    def __init__(self, address, password, use_mesh=1):
        self.address = str(address)
        self.password = str(password)
        self.devices = []
        self.link = None
        self.mesh = use_mesh

    def connect(self):
        if self.link != None:
            return

        for device in self.devices:
            # Try each device in turn - we only need to connect to one to be
            # on the mesh
            try:
                print('name    : %s' % device.name)
                print('type    : %s' % device.type)
                print('mac     : %s' % device.mac)
                print('address : %s' % self.address) 
                print('password: %s' % self.password)
                self.link = dimond.dimond(0x0211, device.mac, self.address, self.password, self, callback)
                self.link.connect()
                break
            except Exception as e:
                print("Failed to connect to %s" % device.mac, e)
                self.link = None
                pass
        if self.link is None:
            raise Exception("Unable to connect to mesh %s" % self.address)

    def send_packet(self, id, command, params):
        self.link.send_packet(id, command, params)

    def update_status(self):
        self.send_packet(0xffff, 0xda, [])

        
class laurel_device:
    def __init__ (self, network, device):
        self.network = network
        self.name = device['name']
        self.id = device['id']
        self.mac = device['mac']
        self.type = device['type']
        self.callback = None
        self.brightness = 0
        self.temperature = 0
        self.red = 0
        self.green = 0
        self.blue = 0
        self.rgb = False

    def set_callback(self, callback, cbargs):
        self.callback = callback
        self.cbargs = cbargs

    def set_temperature(self, temperature):
        self.network.send_packet(self.id, 0xe2, [0x05, temperature])
        self.temperature = temperature

    def set_rgb(self, red, green, blue):
        self.network.send_packet(self.id, 0xe2, [0x04, red, green, blue])
        self.red = red
        self.green = green
        self.blue = blue

    def set_brightness(self, brightness):
        self.network.send_packet(self.id, 0xd2, [brightness])
        self.brightness = brightness

    def set_power(self, power):
        self.network.send_packet(self.id, 0xd0, [int(power)])

    def update_status(self):
        self.network.send_packet(self.id, 0xda, [])

    def supports_temperature(self):
        if self.supports_rgb() or \
           self.type == 5 or \
           self.type == 19 or \
           self.type == 20 or \
           self.type == 80 or \
           self.type == 83 or \
           self.type == 85:
            return True
        return False

    def supports_rgb(self):
        if self.type == 6 or \
           self.type == 7 or \
           self.type == 8 or \
           self.type == 21 or \
           self.type == 22 or \
           self.type == 23:
            return True
        return False
