import json
import urllib.request
import pytest
from bio_knowledge_lab.api import Client, reservation

def test_budget_rejects_before_request(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError("network called")
    monkeypatch.setattr(urllib.request,"urlopen",forbidden)
    client=Client(tmp_path/"ledger.json","test",ceiling=0.001)
    with pytest.raises(RuntimeError,match="预算不足"):
        client.call("hello",tmp_path/"response.json")

def test_unknown_request_keeps_reservation(tmp_path,monkeypatch):
    def timeout(*args,**kwargs): raise TimeoutError()
    monkeypatch.setattr(urllib.request,"urlopen",timeout)
    path=tmp_path/"ledger.json"
    client=Client(path,"test")
    with pytest.raises(RuntimeError): client.call("hello",tmp_path/"response.json")
    value=json.loads(path.read_text())
    assert value["calls"][0]["status"] == "unknown_or_failed"
    assert value["calls"][0]["reserved_cny"] == reservation("hello",4096)
    with pytest.raises(RuntimeError,match="不自动重复"):
        client.call("hello",tmp_path/"response.json")
