import requests
import json
from datetime import datetime

class XChangeRequest:

    base_url = "http://127.0.0.1:8000/api/"

    def __init__(self, token):
        self.token = token
        self.user = self.get_user()

    def send_request(self, endpoint, method, data=None):
        header = {"Authorization": "Token {}".format(self.token),
        "Content-Type": 'application/json'}
        response = None
        url = self.base_url + endpoint
        if method.lower() == "post":
            response = requests.post(url, data=data, headers=header)
        elif method.lower() == "get":
            response = requests.get(url, data=data, headers=header)

        return response
        

    def get_user(self):
        resp = self.send_request("current_user", "GET")

        return json.loads(resp.content)

    def create_trade(self, asset, seller_id, buyer_id, price):

        data = json.dumps({"asset": asset, "seller": seller_id, "buyer": buyer_id, "price":price})

        return self.send_request('trades/', 'POST', data)

    def get_assets_owned(self):
        resp = self.send_request('assets/?owner={}'.format(self.user["id"]), "GET")
        assets = json.loads(resp.content)
        if "results" in assets.keys():
            return assets["results"]
        else:
            return None

    

token = "5749dd765a968290394cdf6cd35ad86240bb2062"

xcreq = XChangeRequest(token)

# user = xcreq.get_user()
print(xcreq.user)

assets_owned=xcreq.get_assets_owned()
print(assets_owned)

resp = xcreq.create_trade({"type":"share", "athlete": 4, "volume": 1.05}, buyer_id=xcreq.user["id"], seller_id=None, price=10.0)
print(resp.status_code)
print(resp.content)


resp = xcreq.create_trade(assets_owned[0]["id"], buyer_id=xcreq.user["id"], seller_id=None, price=10.0)
print(resp.status_code)
print(resp.content)

future = {"type": "future", "buyer": None, "seller": xcreq.user["id"], 
'strike_price': 1.3, 'strike_time': datetime(2020, 8, 2, 10, 45, 0).isoformat(),  
'underlying_asset': {"type":"share", "athlete": 4, "volume": 0.13}}
option = {}
resp = xcreq.create_trade(future, buyer_id=None, seller_id=xcreq.user["id"], price=0.01)
print(resp.status_code)
print(resp.content)

