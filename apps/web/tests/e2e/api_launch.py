# The real dma_api, with Google's IAP key list replaced by the e2e key.
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "api"))
from dma_api import identity
identity._cache["keys"] = json.load(open(os.path.join(os.path.dirname(__file__), "jwks.json")))["keys"]
identity._cache["at"] = time.time() + 10**6
import uvicorn
from dma_api.main import app
uvicorn.run(app, host="127.0.0.1", port=8090, log_level="warning")
