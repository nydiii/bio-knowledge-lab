"""Accountable text-only requests; ledger persists reservations before dispatch.

No automatic retry. Unknown outcomes retain their full worst-case reservation.
The configured ceiling applies to this project's ledger, not other account use.
"""
import contextlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from .io import digest, write_json

MODEL = "deepseek-flash"
PRICE = {"input_cny_per_million": 2, "output_cny_per_million": 8,
         "checked": "2026-11-12", "basis": "peak, no cache discount",
         "source": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"}

def credentials(path=None):
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key and path:
        key = json.loads(Path(path).read_text(encoding="utf-8")).get("api_key")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("未配置 DEEPSEEK_API_KEY；回放模式无需密钥。")
    return key.strip()

def reservation(prompt, max_tokens):
    if not isinstance(max_tokens, int) or not 1 <= max_tokens <= 8192:
        raise ValueError("max_tokens 必须在 1..8192。")
    # Byte bound deliberately overestimates text tokens; includes message overhead.
    return (len(prompt.encode("utf-8")) + 2048) * 2 / 1e6 + max_tokens * 8 / 1e6

@contextlib.contextmanager
def locked(path):
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 30
    while True:
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError("预算账本正被占用；如进程曾异常退出，先核对账本再清理锁。")
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.unlink()

class Client:
    def __init__(self, ledger, key, ceiling=5.0):
        if not 0 < ceiling <= 5:
            raise ValueError("本项目预算必须大于 0 且不超过 5 元。")
        self.ledger, self.key, self.ceiling = Path(ledger), key, ceiling

    def _read(self):
        if self.ledger.exists():
            value = json.loads(self.ledger.read_text(encoding="utf-8"))
            if value["ceiling_cny"] != self.ceiling:
                raise ValueError("不能用不同预算重新打开已有账本。")
            if value.get("halted"):
                raise RuntimeError("预算账本已停止，必须先核查超出预留的实际用量。")
            return value
        return {"ceiling_cny": self.ceiling, "pricing": PRICE, "calls": []}

    def call(self, prompt, response_path, *, max_tokens=4096):
        response_path = Path(response_path)
        prompt_hash = digest(prompt)
        if response_path.exists():
            cached = json.loads(response_path.read_text(encoding="utf-8"))
            if cached["prompt_sha256"] != prompt_hash or cached.get("requested_model") != MODEL:
                raise ValueError("缓存提示或模型不匹配，未发起付费请求。")
            return cached
        reserved = reservation(prompt, max_tokens)
        with locked(self.ledger):
            ledger = self._read()
            # pending / failed / unknown requests stay charged at reservation.
            committed = sum(x.get("charged_upper_cny", x["reserved_cny"]) for x in ledger["calls"])
            if any(x["response_path"] == str(response_path.resolve()) for x in ledger["calls"]):
                raise RuntimeError("此请求已有账本记录但缺失缓存；不自动重复付费，请先核查。")
            if committed + reserved > self.ceiling:
                raise RuntimeError(f"预算不足：已用及预留 {committed:.4f}，本次需预留 {reserved:.4f} 元；未调用。")
            call_id = len(ledger["calls"])
            ledger["calls"].append({"call_id": call_id, "prompt_sha256": prompt_hash,
                "response_path": str(response_path.resolve()), "reserved_cny": reserved,
                "status": "pending", "started_at": datetime.now(timezone.utc).isoformat()})
            write_json(self.ledger, ledger)
        body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                "temperature": 0, "thinking": {"type": "disabled"}, "max_tokens": max_tokens,
                "response_format": {"type": "json_object"}, "stream": False}
        request = urllib.request.Request("https://api.deepseek.com/chat/completions",
            data=json.dumps(body).encode("utf-8"), headers={"Authorization": "Bearer " + self.key,
            "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=180) as r:
                result = json.load(r)
        except Exception as exc:
            with locked(self.ledger):
                ledger = self._read()
                ledger["calls"][call_id].update(status="unknown_or_failed", error_type=type(exc).__name__)
                write_json(self.ledger, ledger)
            raise RuntimeError("API 调用失败，保留全部预算预留且不自动重试；请查看账本。") from None
        usage = result.get("usage", {})
        charged = reserved
        if all(isinstance(usage.get(k), int) and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens")):
            charged = (usage["prompt_tokens"] * 2 + usage["completion_tokens"] * 8) / 1e6
        packet = {"requested_model": MODEL, "prompt_sha256": prompt_hash, "prompt": prompt,
                  "request_settings": {k:v for k,v in body.items() if k != "messages"},
                  "recorded_at": datetime.now(timezone.utc).isoformat(), "response": result,
                  "cost_upper_cny": charged, "pricing": PRICE}
        write_json(response_path, packet)
        with locked(self.ledger):
            ledger = self._read()
            ledger["calls"][call_id].update(status="responded", charged_upper_cny=charged,
                usage=usage, response_id=result.get("id"), served_model=result.get("model"))
            if charged > reserved:
                ledger["halted"] = True
            write_json(self.ledger, ledger)
        if charged > reserved:
            raise RuntimeError("服务方 usage 超出预留假设；已保存响应，停止继续调用并核查计价。")
        return packet

def response_json(packet):
    choice = packet["response"]["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("模型响应未正常结束；保留原响应，不将截断结果作为有效抽取。")
    content = choice["message"].get("content") or ""
    return json.loads(content)
