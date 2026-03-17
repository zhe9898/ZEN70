import urllib.request as r
import json
import sys

try:
    req = r.Request(
        'http://zen70-gateway:8000/api/v1/switches/media', 
        data=json.dumps({'state':'OFF'}).encode(), 
        headers={'Content-Type':'application/json'}
    )
    resp = r.urlopen(req)
    print(resp.read().decode())
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
