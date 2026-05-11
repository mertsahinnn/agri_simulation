import urllib.request
import time

url = "http://127.0.0.1:8000/stream/0"
try:
    print(f"Connecting to {url}")
    req = urllib.request.urlopen(url, timeout=5)
    print("Response code:", req.getcode())
    print("Headers:", req.headers)
    # Read a small chunk
    chunk = req.read(100)
    print("Received chunk size:", len(chunk))
except Exception as e:
    print("Error:", e)
