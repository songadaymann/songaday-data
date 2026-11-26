"""Read contract events, transactions and stored values from public blockchain nodes, with a
cache. Used by sources/sales.py. Nothing here needs an API key or an account.

Nodes (plain JSON-RPC over HTTPS; the first that answers is used):
  ethereum  https://mainnet.gateway.tenderly.co   full history, any block range
            https://rpc.mevblocker.io             full history, 10,000 blocks per request
  optimism  https://optimism.gateway.tenderly.co  full history
            https://mainnet.optimism.io           for block times before June 2023
  zora      https://rpc.zora.energy               full history
  base      https://mainnet.base.org, https://base.public.blockpi.network/v1/rpc/public
            current values only: no free Base node keeps old event history, so on Base
            sales.py reads what the auction contracts themselves store (eth_call)

Everything fetched is cached under cache/sales/, so a rerun with a full cache makes no web
requests.
"""

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "sales"
USER_AGENT = "songaday-data/0.1 (github.com/songadaymann/songaday-data)"
REQUEST_PAUSE = 0.25  # seconds between live requests; one request at a time

# (url, most blocks one eth_getLogs may span; None = no limit)
NODES = {
    "ethereum": [("https://mainnet.gateway.tenderly.co", None),
                 ("https://rpc.mevblocker.io", 10_000)],
    "optimism": [("https://optimism.gateway.tenderly.co", None),
                 ("https://mainnet.optimism.io", 10_000)],
    "zora": [("https://rpc.zora.energy", None)],
    "base": [("https://mainnet.base.org", 10_000),
             ("https://base.public.blockpi.network/v1/rpc/public", 5_000)],
}

# Which node takes batched requests first (index into NODES). Tenderly allows few calls a
# minute without a key, so on Ethereum batches go to mevblocker and Tenderly keeps the wide
# event scans.
BATCH_FIRST = {"ethereum": 1}

OFFLINE = False  # set by sales.py --offline: never touch the network
_session = None
_last_request = 0.0


class Offline(RuntimeError):
    """Raised when --offline needs something that isn't cached."""


class RpcError(RuntimeError):
    pass


def _post(url, payload, attempts=5):
    global _session, _last_request
    if OFFLINE:
        raise Offline(f"not cached and --offline is set: {url}")
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = USER_AGENT
    last = None
    for attempt in range(attempts):
        wait = REQUEST_PAUSE - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()
        try:
            r = _session.post(url, json=payload, timeout=90)
        except requests.RequestException as err:
            last = err
            time.sleep(2 + attempt * 3)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            last = f"HTTP {r.status_code}"
            time.sleep(2 + attempt * 4)
            continue
        try:
            return r.json()
        except ValueError:
            last = f"HTTP {r.status_code}, not JSON"
            time.sleep(2 + attempt * 3)
    raise RpcError(f"{url}: {last}")


def rpc(chain, method, params, node=0):
    """One JSON-RPC call. Returns the result, or raises RpcError with the node's message."""
    url = NODES[chain][node][0]
    answer = _post(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if isinstance(answer, dict) and "result" in answer and "error" not in answer:
        return answer["result"]
    raise RpcError(f"{url} {method}: {json.dumps(answer)[:300]}")


def rpc_any(chain, method, params):
    """rpc() on each of the chain's nodes in turn until one answers. A call the contract
    itself rejects ("execution reverted") is not asked again."""
    last = None
    for node in sorted(range(len(NODES[chain])), key=lambda n: n != BATCH_FIRST.get(chain, 0)):
        try:
            return rpc(chain, method, params, node)
        except RpcError as err:
            last = err
            if "revert" in str(err).lower():
                break
    raise last


def batch(chain, calls, size=15):
    """Many JSON-RPC calls, `size` per HTTP request. calls: [(method, params)]. Results in
    order. A call that comes back with an error or nothing is asked again, one at a time, on
    each node in turn; it gives None only if every node refuses it."""
    out = []
    for i in range(0, len(calls), size):
        chunk = calls[i:i + size]
        payload = [{"jsonrpc": "2.0", "id": n, "method": m, "params": p}
                   for n, (m, p) in enumerate(chunk)]
        got = {}
        order = sorted(range(len(NODES[chain])), key=lambda n: n != BATCH_FIRST.get(chain, 0))
        for node in order:
            try:
                answer = _post(NODES[chain][node][0], payload, attempts=2)
            except RpcError:
                continue
            if isinstance(answer, list):
                for a in answer:
                    if isinstance(a, dict) and a.get("result") is not None and "error" not in a:
                        got[a.get("id")] = a["result"]
                break
        for n, (m, p) in enumerate(chunk):
            if n not in got:
                for attempt in range(3):
                    try:
                        result = rpc_any(chain, m, p)
                    except RpcError as err:
                        if "revert" in str(err).lower():
                            break
                        time.sleep(1 + attempt * 2)
                        continue
                    if result is not None:
                        got[n] = result
                        break
                    time.sleep(1 + attempt * 2)
        out += [got.get(n) for n in range(len(chunk))]
    return out


def _read(path):
    return json.loads(path.read_text()) if path.exists() else None


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")))
    tmp.replace(path)


def latest_block(chain):
    return int(rpc_any(chain, "eth_blockNumber", []), 16)


def _slim(row):
    stamp = row.get("blockTimestamp")
    return {
        "blockNumber": int(row["blockNumber"], 16),
        "timeStamp": int(stamp, 16) if stamp else None,
        "transactionHash": row["transactionHash"],
        "logIndex": int(row["logIndex"], 16),
        "address": row["address"].lower(),
        "topics": row["topics"],
        "data": row["data"],
    }


def _scan(chain, address, topics, start, head):
    """eth_getLogs from start to head, in pieces no wider than the node allows. A range the
    node calls too wide, or that returns too much, is halved and tried again; a node that is
    rate-limiting hands over to the next one."""
    node = 0
    limit = NODES[chain][node][1]
    out = []
    step = limit or (head - start + 1)
    lo = start
    while lo <= head:
        hi = min(head, lo + step - 1)
        flt = {"address": address, "fromBlock": hex(lo), "toBlock": hex(hi)}
        if topics:
            flt["topics"] = topics
        try:
            rows = rpc(chain, "eth_getLogs", [flt], node)
        except RpcError as err:
            busy = "429" in str(err) or "rate limit" in str(err).lower()
            if busy and node + 1 < len(NODES[chain]):
                node += 1
                limit = NODES[chain][node][1]
                step = min(step, limit) if limit else step
                continue
            if hi > lo and not busy:  # too wide or too many results: halve and try again
                step = max(1, (hi - lo + 1) // 2)
                continue
            raise err
        out += [_slim(r) for r in rows]
        lo = hi + 1
        if limit is None or step < limit:
            step = min(step * 2, limit or (head - lo + 1) or 1)
    return out


def logs(chain, address, name, topics=None, start=0, refresh=False):
    """Every log from `address` (a string or a list) matching `topics`, oldest first.

    Cached in cache/sales/logs/<chain>/<name>.json with the block the scan reached. With
    refresh=True the scan continues from there to the chain head; otherwise the cached list
    is returned untouched.
    """
    path = CACHE_DIR / "logs" / chain / f"{name}.json"
    cached = _read(path)
    if cached and (not refresh or OFFLINE):
        return cached["logs"]
    if cached is None and OFFLINE:
        raise Offline(f"no cached logs for {chain}/{name}")
    out = cached["logs"] if cached else []
    begin = cached["scanned_to"] + 1 if cached else start
    head = latest_block(chain) - 12  # stay a few blocks behind the tip
    if begin <= head:
        new = _scan(chain, address, topics, begin, head)
        missing = sorted({l["blockNumber"] for l in new if l["timeStamp"] is None})
        if missing:
            stamps = block_times(chain, missing)
            for l in new:
                if l["timeStamp"] is None:
                    l["timeStamp"] = stamps[l["blockNumber"]]
        out += new
        out.sort(key=lambda l: (l["blockNumber"], l["logIndex"]))
        _write(path, {"chain": chain, "address": address, "topics": topics,
                      "scanned_to": head, "logs": out})
    return out


def block_times(chain, numbers):
    """{block number: unix time}, cached in cache/sales/blocks/<chain>.json."""
    path = CACHE_DIR / "blocks" / f"{chain}.json"
    known = _read(path) or {}
    need = [n for n in numbers if str(n) not in known]
    if need:
        answers = batch(chain, [("eth_getBlockByNumber", [hex(n), False]) for n in need])
        for n, block in zip(need, answers):
            if block is None:
                raise RpcError(f"{chain}: no block {n}")
            known[str(n)] = int(block["timestamp"], 16)
        _write(path, known)
    return {n: known[str(n)] for n in numbers}


def receipts(chain, hashes):
    """{tx hash: {from, to, value (wei, int), logs}} for each hash, cached one file per
    transaction in cache/sales/tx/<chain>/."""
    out, need = {}, []
    for h in hashes:
        cached = _read(CACHE_DIR / "tx" / chain / f"{h}.json")
        if cached:
            out[h] = cached
        elif h not in need:
            need.append(h)
    if need and OFFLINE:
        raise Offline(f"{len(need)} {chain} transactions are not cached")
    for i in range(0, len(need), 15):
        part = need[i:i + 15]
        txs = batch(chain, [("eth_getTransactionByHash", [h]) for h in part])
        recs = batch(chain, [("eth_getTransactionReceipt", [h]) for h in part])
        for h, t, r in zip(part, txs, recs):
            if t is None or r is None:
                raise RpcError(f"{chain}: transaction {h} not found")
            slim = {
                "hash": h,
                "from": t["from"].lower(),
                "to": (t.get("to") or "").lower(),
                "value": int(t["value"], 16),
                "input4": t["input"][:10],
                "blockNumber": int(t["blockNumber"], 16),
                "status": int(r.get("status", "0x1"), 16),
                "logs": [{"address": l["address"].lower(), "topics": l["topics"],
                          "data": l["data"], "logIndex": int(l["logIndex"], 16)}
                         for l in r["logs"]],
            }
            _write(CACHE_DIR / "tx" / chain / f"{h}.json", slim)
            out[h] = slim
        if len(need) > 100 and (i // 15) % 10 == 0:
            print(f"    {chain}: {min(i + 15, len(need))}/{len(need)} transactions", flush=True)
    return out


def calls(chain, requests_):
    """eth_call at the latest block for each (to, data). Returns the hex results in order
    (None where the call reverts). Not cached here: sales.py stores what it reads."""
    return batch(chain, [("eth_call", [{"to": to, "data": data}, "latest"])
                         for to, data in requests_])


# -- small decoding helpers ---------------------------------------------------------------

def word(data, i):
    """The i-th 32-byte word of hex data, as an int."""
    return int(data[2 + 64 * i: 66 + 64 * i] or "0", 16)


def words(data):
    return [word(data, i) for i in range((len(data) - 2) // 64)]


def topic_int(topic):
    return int(topic, 16)


def topic_addr(topic):
    return "0x" + topic[-40:].lower()


def pad_int(n):
    return f"{n:064x}"


def pad_addr(address):
    return address.lower().replace("0x", "").rjust(64, "0")
