"""What each Song A Day song sold for as an NFT: one row per sale, first sales and resales.

Song A Day songs have been sold as one-of-a-kind NFTs since 2021, through a different contract
every year or two. Each contract is the record of its own sales, so this script reads them
directly from the blockchains and writes dataset/sales.csv. No API key, no account, no paid
service.

Where each figure comes from
----------------------------
price, buyer, seller, tx_hash
    The sale's own record on chain. Which record depends on the venue (see VENUES below and
    `--contracts`):
    - opensea_2021   songs 1-730, sold from Jonathan's OpenSea wallet in 2021. The token moves
                     in a TransferSingle event of OpenSea's shared storefront; the price is the
                     OrdersMatched event of OpenSea's exchange in the same transaction. Which
                     storefront token is which song comes from sources/opensea_2021_tokens.csv
                     (the list songaday.world used to upgrade those tokens in 2022).
    - mint_2021      songs 731-4748 (3,978 of them), all on 31 December 2021: the
                     public mint of the main collection, publicMint, 0.2 ETH a song. Each
                     Transfer from the zero address in a publicMint transaction is one sale;
                     the price is the ETH sent divided by the songs minted in it.
    - zora_2022      songs 4749-5118, 2022. Zora's auction house: AuctionEnded gives the
                     winner and the amount; AuctionBid events give the number of bids.
    - gbm_v1, gbm_v2 songs 5119-5478, 2023. GBM auctions on Ethereum: Auction_Initialized
                     ties an auction to a song, the last Auction_BidPlaced is the winning bid.
    - gbm_zora       songs 5530-5844, 2024, the same GBM auction on the Zora network.
    - gbm_base       songs 5845-6500, 2025-2026, the same on Base. No free Base node keeps old
                     events, so these are read from what the contract stores for each song:
                     getAuctionIDSongADao, getAuctionHighestBid, getAuctionHighestBidder,
                     getAuctionEndTime. There is no tx_hash and no bid count for these rows.
    - auction_2026   songs 6501 on, from 2026-10-19, on Base: getAuction(song) on the
                     SongADayAuction contract (highest bid, bidder, end time, settled).
    - resales        every later sale of a song in the main Song A Day collection on Ethereum
                     (0x19b7...1C45): each Transfer of a song is looked up in its transaction
                     for a marketplace sale event (OpenSea's old exchange and Seaport, Blur,
                     LooksRare). Transfers with no such event are not sales as far as this
                     script can tell: gifts, wallet moves, pool swaps. They are counted in the
                     report, not written.
date
    The UTC day of the sale. For 2021 OpenSea sales and resales, the transaction's block
    time. For 2022 Zora auctions, the winning bid's block time (settlement was often days
    later). For GBM and 2026 auctions, the auction's end time as the contract stores it.
price_usd, eth_usd
    price x that UTC day's ETH price: the daily closing price of ETH-USD on Coinbase
    (https://api.exchange.coinbase.com/products/ETH-USD/candles, public, no key). WETH and
    Blur's ETH pool are ETH one for one.
kind
    first_sale: the first time the song was sold, by Jonathan, the SongADAO treasury or one of
    the auction contracts. resale: every sale after that, and any sale between other wallets.

Not covered (see dataset/README.md, "Sales"): songs 5479-5529 (sound.xyz, 2023-2024), every
edition (many copies at a small price: Optimism, Zora, Base and the 2026 patron editions),
resales of the 2021 OpenSea tokens before they were upgraded, resales on the Zora and Base
networks, pool swaps, private sales.

Nodes used are listed in sources/chainlogs.py. Everything fetched is cached under
cache/sales/; with a full cache the script makes no web requests and writes the same file.

Run:  .venv/bin/python sources/sales.py              (fetches only what isn't cached)
      .venv/bin/python sources/sales.py --offline    (cache only, no network)
      .venv/bin/python sources/sales.py --refresh    (also read events and auctions newer
                                                      than the cache)
      .venv/bin/python sources/sales.py --contracts  (print the list of contracts and stop)
"""

import argparse
import collections
import csv
import datetime as dt
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

import requests

import chainlogs as chain
from chainlogs import pad_addr, pad_int, topic_addr, topic_int, word, words

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "sales"
OUT_CSV = ROOT / "dataset" / "sales.csv"
SONGS_CSV = ROOT / "dataset" / "songs.csv"
OPENSEA_TOKENS = Path(__file__).resolve().parent / "opensea_2021_tokens.csv"
USER_AGENT = chain.USER_AGENT

# ---- addresses ------------------------------------------------------------------------------

SONGADAY = "0x19b703f65aa7e1e775bd06c2aa0d0d08c80f1c45"  # the main collection, Ethereum
TREASURY = "0x2a2c412c440dfb0e7cae46eff581e3e26afd1cd0"  # SongADAO treasury
OPERATOR = "0xaba3a04fc85fd7bbc2538e708e9e30bbc59899c3"  # mints and delivers since 2025
CREATOR = "0x3d9456ad6463a77bd77123cb4836e463030bfab4"  # Jonathan's wallet (OpenSea, GBM)
OURS = {TREASURY, OPERATOR, CREATOR}

OPENSTORE = "0x495f947276749ce646f68ac8c248420045cb7b5e"  # OpenSea shared storefront
WYVERN = {"0x7be8076f4ea4a4ad08075c2508e481d6c946d12b",  # OpenSea exchange v1
          "0x7f268357a8c2552623316e2562d90e642bb538e5"}  # OpenSea exchange v2
ZORA_AUCTION_HOUSE = "0xe468ce99444174bd3bbbed09209577d25d1ad673"
GBM_V1 = "0xd736d2c76fba2ba5a217fd4edfa1b231deeeb29d"
GBM_V2 = "0x1c51abab1160879e697733124da80e4072590bbd"
GBM_ZORA = "0x2cc2d8256798b35a4c1d181284127baaca750014"
GBM_BASE = ["0xeaedade6a47b08f21c6c0b319024c6feda3e6539",
            "0xd7829f0efc16086a91cf211cfbb0e4ef29d16bee"]
AUCTION_2026 = "0xfd8126142d2c6c4fa4c0dfe6694ff71413666d38"
OPENSEA_TRANSFER_HELPER = "0x0000000000c2d145a2526bd8c716263bfebe1a72"  # bulk transfers, no sale
BLUR_V1 = "0x000000000000ad05ccc4f10045630fb830b95127"
BLUR_V2 = "0xb2ecfe4e4d61f8790bbb9de2d1259b9e2410cea5"
LOOKSRARE = "0x59728544b08ab483533076417fbbb2fd0b17ce3a"

WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
BLUR_POOL = "0x0000000000a39bb272e79075ade125fd351887ac"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
ZERO = "0x" + "0" * 40

# Contracts whose custody moves are part of a first sale, never a resale.
VENUE_CONTRACTS = {ZORA_AUCTION_HOUSE, GBM_V1, GBM_V2}

# ---- event topics (keccak-256 of the signature) ------------------------------------------------

T_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
# Transfer(address,address,uint256)
T_TRANSFER_SINGLE = "0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62"
# TransferSingle(address,address,address,uint256,uint256)
T_WYVERN_MATCHED = "0xc4109843e0b7d514e4c093114b863f8e7d8d9a458c372cd51bfe526b588006c9"
# OrdersMatched(bytes32,bytes32,address,address,uint256,bytes32)
T_SEAPORT_FULFILLED = "0x9d9af8e38d66c62e2c12f0225249fd9d721c54b83f48d9352c97c6cacdcb6f31"
# OrderFulfilled(bytes32,address,address,address,(uint8,address,uint256,uint256)[],
#                (uint8,address,uint256,uint256,address)[])   every Seaport version
T_BLUR_MATCHED = "0x61cbb2a3dee0b6064c2e681aadd61677fb4ef319f0b547508d495626f5a62f64"
# Blur v1 OrdersMatched(address,address,Order,bytes32,Order,bytes32)
T_BLUR2 = {"0x1d5e12b51dee5e4d34434576c3fb99714a85f57b0fd546ada4b0bddd736d12b2",
           "0x7dc5c0699ac8dd5250cbe368a2fc3b4a2daadb120ad07f6cccea29f83482686e",
           "0x0fcf17fac114131b10f37b183c6a60f905911e52802caeeb3e6ea210398b81ab"}
# Blur v2 Execution721Packed / Execution721MakerFeePacked / Execution721TakerFeePacked
T_LOOKS = {"0x95fb6205e23ff6bda16a2d1dba56b9ad7c783f67c96fa149785052f47696f2be",   # TakerBid
           "0x68cd251d4d267c6e2034ff0088b990352b97b2002c0476587d0c4da889c11330"}   # TakerAsk
T_ZORA_ENDED = "0x4f35fb3ea0081b3ccbe8df613cab0f9e1694d50a025e0aa09b88a86a3d07c2de"
# AuctionEnded(uint256,uint256,address,address,address,address,uint256,uint256,address)
T_ZORA_BID = "0xda6b779568630ce5e5658b317174df474d5b335541ed9471bd8424a017f3be6d"
# AuctionBid(uint256,uint256,address,address,uint256,bool,bool)
T_GBM_INIT = "0xb9d707ce49c63f003358ae85d59fc5c7762e8de3ce5a41f6bb0e7fb5e1a4cd85"
# Auction_Initialized(uint256,uint256,address,bytes4)
T_GBM_BID = "0x1cd77ec6c10f614681f30c7aa33ebc645b4d597aaf7039f6210e71d0e15c9181"
# Auction_BidPlaced(uint256,address,uint256)
T_GBM_CLAIMED = "0xb1270969942994e0432341247ac48a59854a62941bad895492ab9e45418582db"
# Auction_Claimed(uint256)

# ---- function selectors ---------------------------------------------------------------------

F_PUBLIC_MINT = "0x2db11544"  # publicMint(uint256), main collection
F_GBM_ID = "0x78370d7b"       # getAuctionIDSongADao(address,uint256)
F_GBM_BID = "0xc26e748c"      # getAuctionHighestBid(uint256)
F_GBM_BIDDER = "0xdfab114b"   # getAuctionHighestBidder(uint256)
F_GBM_END = "0x930e79f1"      # getAuctionEndTime(uint256)
F_GBM_CLAIMED = "0x9b7a7009"  # wasClaimed(uint256)
F_GET_AUCTION = "0x78bd7935"  # getAuction(uint256), SongADayAuction

GBM_BASE_SONGS = (5845, 6500)   # songaday.world's ranges (components/PurchaseInterface.tsx)
AUCTION_2026_FIRST = 6501
TEST_TOKENS_BELOW = 5100        # GBM auctions for lower numbers on Zora were tests

# The list shown by --contracts and copied into sources/README.md. "sale" says how a sale shows
# up; "status" says whether this script reads it.
VENUES = [
    ("opensea_2021", "ethereum", OPENSTORE, "2021", "1-730",
     "OpenSea shared storefront: TransferSingle from Jonathan's wallet + OrdersMatched on "
     "OpenSea's exchange (0x7be8...d12b)", "read"),
    ("mint_2021", "ethereum", SONGADAY, "2021-12-31", "731-4748",
     "Main collection, publicMint at 0.2 ETH a song: Transfer from the zero address in a "
     "transaction that sends ETH", "read"),
    ("claim_2022", "ethereum", SONGADAY, "2021-12 to 2023", "1-730",
     "Main collection, publicClaim: the 2021 tokens swapped one for one, no payment", "not a sale"),
    ("zora_2022", "ethereum", ZORA_AUCTION_HOUSE, "2022", "4749-5118",
     "Zora auction house: AuctionEnded (winner, amount), AuctionBid", "read"),
    ("gbm_v1", "ethereum", GBM_V1, "2023", "5119-5202",
     "GBM auction: Auction_Initialized, Auction_BidPlaced, Auction_Claimed", "read"),
    ("gbm_v2", "ethereum", GBM_V2, "2023", "5203-5478",
     "GBM auction: same events", "read"),
    ("soundxyz", "ethereum", "(one contract per song)", "2023-2024", "5479-5529",
     "sound.xyz editions; the original went to one edition buyer picked at random", "NOT READ"),
    ("gbm_zora", "zora", GBM_ZORA, "2024", "5530-5844",
     "GBM auction on Zora: same events", "read"),
    ("gbm_base", "base", " and ".join(GBM_BASE), "2025-2026", "5845-6500",
     "GBM auction on Base: stored values getAuctionHighestBid / Bidder / EndTime", "read"),
    ("auction_2026", "base", AUCTION_2026, "2026-", "6501-",
     "SongADayAuction: stored getAuction(song); events BidPlaced, AuctionSettled", "read"),
    ("resale", "ethereum", SONGADAY, "2022-", "any",
     "Main collection Transfer + a sale event of OpenSea (old exchange, Seaport), Blur or "
     "LooksRare in the same transaction", "read"),
    ("editions_optimism", "optimism", "0x9c17564ccaa0bae1d3883251cae70ca86ef3ec41", "?", "?",
     "Editions (many copies per song): Mint_Initialized, TransferSingle", "NOT READ"),
    ("editions_zora_base", "zora, base", "0xb3bad5fe12268edc8a52ff786076c1d1fa92ef0d (Base)",
     "2024-2026", "5530-6500", "Zora-protocol editions sold beside each GBM auction: Purchased",
     "NOT READ"),
    ("editions_2026", "ethereum", "0x3e290d6f5c66b1faabd072db9e0d223edefc7ab5", "2026-",
     "6501-", "Patron editions: EditionMinted (paid or supporter)", "NOT READ"),
]

COLUMNS = ["number", "date", "kind", "venue", "chain", "contract", "price", "currency",
           "eth_usd", "price_usd", "buyer", "seller", "tx_hash", "bids", "source", "note"]

REFRESH = False


def day(stamp):
    return dt.datetime.fromtimestamp(stamp, dt.timezone.utc).date().isoformat()


def eth(wei):
    """Wei as a plain decimal string of ETH, no float rounding."""
    text = format(Decimal(wei) / Decimal(10 ** 18), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


# ---- ETH price ------------------------------------------------------------------------------

def eth_usd_by_day():
    """{YYYY-MM-DD: ETH-USD daily close on Coinbase}, cached in cache/sales/eth-usd.json.
    Days already cached are never asked for again, except the last three (still settling)."""
    path = CACHE_DIR / "eth-usd.json"
    known = json.loads(path.read_text()) if path.exists() else {}
    if chain.OFFLINE:
        return known
    today = dt.datetime.now(dt.timezone.utc).date()
    start = dt.date(2021, 1, 1)
    if known:
        start = max(start, dt.date.fromisoformat(max(known)) - dt.timedelta(days=3))
    if known and not REFRESH and dt.date.fromisoformat(max(known)) >= today:
        return known
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    while start <= today:
        end = min(today, start + dt.timedelta(days=299))
        r = session.get("https://api.exchange.coinbase.com/products/ETH-USD/candles",
                        params={"granularity": 86400, "start": f"{start}T00:00:00Z",
                                "end": f"{end}T00:00:00Z"}, timeout=60)
        r.raise_for_status()
        for stamp, _low, _high, _open, close, _volume in r.json():
            known[day(stamp)] = close
        start = end + dt.timedelta(days=1)
        time.sleep(0.4)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(known.items())), separators=(",", ":")))
    return known


# ---- 2021: OpenSea shared storefront ---------------------------------------------------------

def opensea_2021():
    tokens = {}
    with OPENSEA_TOKENS.open() as f:
        for row in csv.DictReader(f):
            tokens[int(row["openstore_token_id"])] = int(row["number"])
    moves = chain.logs("ethereum", OPENSTORE, "openstore-from-creator",
                       topics=[T_TRANSFER_SINGLE, None, "0x" + pad_addr(CREATOR)],
                       start=10_000_000, refresh=REFRESH)
    receipts = chain.receipts("ethereum", list(dict.fromkeys(m["transactionHash"] for m in moves)))
    rows, skipped = [], collections.Counter()
    for tx_hash in dict.fromkeys(m["transactionHash"] for m in moves):
        tx = receipts[tx_hash]
        pending = []  # storefront transfers from the creator waiting for their OrdersMatched
        stamp = next(m["timeStamp"] for m in moves if m["transactionHash"] == tx_hash)
        paid_weth = any(l["address"] == WETH and l["topics"][0] == T_TRANSFER for l in tx["logs"])
        matched = False
        for log in tx["logs"]:
            if (log["address"] == OPENSTORE and log["topics"][0] == T_TRANSFER_SINGLE
                    and topic_addr(log["topics"][2]) == CREATOR):
                pending.append(log)
            elif log["address"] in WYVERN and log["topics"][0] == T_WYVERN_MATCHED:
                matched = True
                price = word(log["data"], 2)
                for move in pending:
                    token = word(move["data"], 0)
                    if token not in tokens:
                        skipped["sold on OpenSea but not one of the 730 songs"] += 1
                        continue
                    rows.append({
                        "number": tokens[token], "when": stamp, "date": day(stamp),
                        "venue": "opensea_2021",
                        "chain": "ethereum", "contract": OPENSTORE,
                        "wei": price // len(pending), "currency": "WETH" if paid_weth else "ETH",
                        "buyer": topic_addr(move["topics"][3]), "seller": CREATOR,
                        "tx_hash": tx_hash, "bids": "", "source": "events",
                        "note": "sold in a bundle; price split evenly" if len(pending) > 1 else "",
                    })
                pending = []
        if not matched:
            skipped["moved out of Jonathan's OpenSea wallet with no sale (gift or transfer)"] += len(pending)
    return rows, skipped


# ---- December 2021: the main collection's public mint -----------------------------------------

def songaday_transfers():
    return chain.logs("ethereum", SONGADAY, "songaday-transfer", topics=[T_TRANSFER],
                      start=13_900_000, refresh=REFRESH)


def mint_2021():
    mints = [t for t in songaday_transfers() if topic_addr(t["topics"][1]) == ZERO]
    receipts = chain.receipts("ethereum", list(dict.fromkeys(m["transactionHash"] for m in mints)))
    per_tx = collections.Counter(m["transactionHash"] for m in mints)
    rows, skipped = [], collections.Counter()
    for m in mints:
        tx = receipts[m["transactionHash"]]
        if tx["input4"] != F_PUBLIC_MINT or not tx["value"]:
            skipped["minted without payment (daily mints to the treasury, 2021 tokens "
                    "upgraded)"] += 1
            continue
        rows.append({
            "number": topic_int(m["topics"][3]), "when": m["timeStamp"],
            "date": day(m["timeStamp"]), "venue": "mint_2021", "chain": "ethereum", "contract": SONGADAY,
            "wei": tx["value"] // per_tx[m["transactionHash"]], "currency": "ETH",
            "buyer": topic_addr(m["topics"][2]), "seller": TREASURY,
            "tx_hash": m["transactionHash"], "bids": "", "source": "events", "note": "",
        })
    return rows, skipped


# ---- 2022: Zora auction house ----------------------------------------------------------------

def zora_2022():
    only_ours = [None, None, "0x" + pad_addr(SONGADAY)]
    ended = chain.logs("ethereum", ZORA_AUCTION_HOUSE, "zora-ended",
                       topics=[T_ZORA_ENDED] + only_ours, start=13_900_000, refresh=REFRESH)
    bids = chain.logs("ethereum", ZORA_AUCTION_HOUSE, "zora-bid",
                      topics=[T_ZORA_BID] + only_ours, start=13_900_000, refresh=REFRESH)
    by_auction = collections.defaultdict(list)
    for bid in bids:
        by_auction[bid["topics"][1]].append(bid)
    rows = []
    for log in ended:
        owner, _curator, winner, amount, curator_fee, _currency = words(log["data"])[:6]
        auction_bids = by_auction[log["topics"][1]]
        last = auction_bids[-1] if auction_bids else log
        rows.append({
            "number": topic_int(log["topics"][2]), "when": last["timeStamp"],
            "date": day(last["timeStamp"]), "venue": "zora_2022", "chain": "ethereum", "contract": ZORA_AUCTION_HOUSE,
            "wei": amount + curator_fee, "currency": "ETH",
            "buyer": "0x" + pad_addr(hex(winner))[-40:], "seller": "0x" + pad_addr(hex(owner))[-40:],
            "tx_hash": last["transactionHash"], "bids": len(auction_bids), "source": "events",
            "note": "",
        })
    return rows, collections.Counter()


# ---- stored values (eth_call), cached per venue ------------------------------------------------

def stored(name):
    path = CACHE_DIR / "state" / f"{name}.json"
    return path, (json.loads(path.read_text()) if path.exists() else {})


def save_stored(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":"), sort_keys=True))


def is_final(entry):
    """Stored values read after the auction ended can't change any more: nobody can bid."""
    return entry.get("end") and entry.get("read", 0) >= entry["end"]


def needs_reading(entry, now):
    """Not read yet; or read while the auction was running and it has ended since; or, with
    --refresh, not yet collected or settled (only the note depends on that)."""
    if entry is None:
        return True
    if not is_final(entry):
        return entry["end"] <= now or REFRESH
    return REFRESH and not (entry.get("claimed") or entry.get("settled"))


def read_gbm(chain_name, contract, auction_ids, known, now, has_claimed=False):
    """highest bid, bidder and end time for each auction id (hex words), plus wasClaimed on
    the contracts that have it (Base)."""
    need = [a for a in auction_ids if needs_reading(known.get(a), now)]
    if chain.OFFLINE:
        if [a for a in need if a not in known]:
            raise chain.Offline(f"some {chain_name} GBM auctions are not cached")
        need = []
    for i in range(0, len(need), 60):
        part = need[i:i + 60]
        fns = (F_GBM_BID, F_GBM_BIDDER, F_GBM_END) + ((F_GBM_CLAIMED,) if has_claimed else ())
        answers = chain.calls(chain_name, [(contract, f + a) for a in part for f in fns])
        for n, a in enumerate(part):
            bid, bidder, end = answers[len(fns) * n: len(fns) * n + 3]
            claimed = answers[len(fns) * n + 3] if has_claimed else None
            if bid is None or bidder is None or end is None:
                raise chain.RpcError(f"{chain_name} {contract}: auction {a} could not be read")
            known[a] = {"bid": str(int(bid, 16)), "bidder": "0x" + bidder[-40:],
                        "end": int(end, 16), "read": now,
                        "claimed": None if claimed is None else bool(int(claimed, 16))}
    return known


# ---- 2023-2024: GBM auctions on Ethereum and Zora -----------------------------------------------

def gbm_events(venue, chain_name, contract, start):
    logs = chain.logs(chain_name, contract, venue.replace("_", "-"), start=start, refresh=REFRESH)
    auctions = {}
    for log in logs:
        topic = log["topics"][0]
        if topic == T_GBM_INIT:
            auctions[log["topics"][1]] = {
                "number": topic_int(log["topics"][2]), "collection": topic_addr(log["topics"][3]),
                "bids": [], "claimed": False}
        elif topic == T_GBM_BID and log["topics"][1] in auctions:
            auctions[log["topics"][1]]["bids"].append(log)
        elif topic == T_GBM_CLAIMED and log["topics"][1] in auctions:
            auctions[log["topics"][1]]["claimed"] = True
    auctions = {a: v for a, v in auctions.items() if v["collection"] == SONGADAY
                and (chain_name == "ethereum" or v["number"] > TEST_TOKENS_BELOW)}
    now = int(time.time())
    path, known = stored(venue)
    before = json.dumps(known, sort_keys=True)
    known = read_gbm(chain_name, contract, [a[2:] for a in auctions], known, now)
    if json.dumps(known, sort_keys=True) != before:
        save_stored(path, known)
    rows, skipped = [], collections.Counter()
    for auction_id, auction in auctions.items():
        state = known[auction_id[2:]]
        if not auction["bids"]:
            skipped["auction ended with no bids"] += 1
            continue
        last = auction["bids"][-1]
        amount = word(last["data"], 0)
        if int(state["bid"]) != amount or state["bidder"] != topic_addr(last["topics"][2]):
            raise SystemExit(f"{venue}: song {auction['number']}: the last bid event and the "
                             "contract's stored highest bid disagree")
        if not is_final(state):
            skipped["auction still running when last read"] += 1
            continue
        rows.append({
            "number": auction["number"], "when": state["end"], "date": day(state["end"]),
            "venue": venue,
            "chain": chain_name, "contract": contract, "wei": amount, "currency": "ETH",
            "buyer": state["bidder"], "seller": TREASURY, "tx_hash": last["transactionHash"],
            "bids": len(auction["bids"]), "source": "events",
            "note": "" if auction["claimed"] else "won but never collected from the auction contract",
        })
    return rows, skipped


# ---- 2025-2026: GBM auctions on Base (stored values only) ---------------------------------------

def gbm_base(last_song):
    now = int(time.time())
    first, last = GBM_BASE_SONGS
    last = min(last, last_song)
    rows, skipped = [], collections.Counter()
    for contract in GBM_BASE:
        path, known = stored("gbm_base-" + contract[:8])
        before = json.dumps(known, sort_keys=True)
        ids = known.setdefault("ids", {})
        need = [n for n in range(first, last + 1) if str(n) not in ids]
        if need and chain.OFFLINE:
            raise chain.Offline(f"{len(need)} Base GBM auction ids are not cached")
        for i in range(0, len(need), 100):
            part = need[i:i + 100]
            answers = chain.calls("base", [(contract, F_GBM_ID + pad_addr(SONGADAY) + pad_int(n))
                                           for n in part])
            for n, answer in zip(part, answers):
                if answer is None:
                    raise chain.RpcError(f"base {contract}: no auction id for song {n}")
                ids[str(n)] = answer[2:]
        auctions = known.setdefault("auctions", {})
        live = [a for a in ids.values() if int(a, 16)]
        read_gbm("base", contract, live, auctions, now, has_claimed=True)
        if json.dumps(known, sort_keys=True) != before:
            save_stored(path, known)
        for number in range(first, last + 1):
            auction_id = ids[str(number)]
            if not int(auction_id, 16):
                continue  # this contract never auctioned this song
            state = auctions[auction_id]
            if int(state["bid"]) == 0:
                skipped["auction ended with no bids"] += 1
                continue
            if not is_final(state):
                skipped["auction still running when last read"] += 1
                continue
            rows.append({
                "number": number, "when": state["end"], "date": day(state["end"]),
                "venue": "gbm_base",
                "chain": "base", "contract": contract, "wei": int(state["bid"]),
                "currency": "ETH", "buyer": state["bidder"], "seller": TREASURY, "tx_hash": "",
                "bids": "", "source": "stored_values",
                "note": "" if state["claimed"] is not False
                        else "won but never collected from the auction contract",
            })
    return rows, skipped


# ---- 2026: SongADayAuction on Base ---------------------------------------------------------------

def auction_2026(last_song):
    now = int(time.time())
    path, known = stored("auction_2026")
    before = json.dumps(known, sort_keys=True)
    need = [n for n in range(AUCTION_2026_FIRST, last_song + 1)
            if needs_reading(known.get(str(n)), now)]
    if chain.OFFLINE:
        if [n for n in need if str(n) not in known]:
            raise chain.Offline("some 2026 auctions are not cached")
        need = []
    if need:
        answers = chain.calls("base", [(AUCTION_2026, F_GET_AUCTION + pad_int(n)) for n in need])
        for n, answer in zip(need, answers):
            if answer is None:
                raise chain.RpcError(f"base: getAuction({n}) could not be read")
            w = words(answer)
            known[str(n)] = {"start": w[1], "end": w[2], "bid": str(w[5]), "read": now,
                             "bidder": "0x" + f"{w[6]:040x}", "recipient": "0x" + f"{w[7]:040x}",
                             "settled": bool(w[9]), "cancelled": bool(w[10])}
    if json.dumps(known, sort_keys=True) != before:
        save_stored(path, known)
    rows, skipped = [], collections.Counter()
    for n in range(AUCTION_2026_FIRST, last_song + 1):
        state = known.get(str(n))
        if state is None or state["end"] == 0:
            skipped["no auction created"] += 1
        elif state["cancelled"]:
            skipped["auction cancelled"] += 1
        elif not is_final(state):
            skipped["auction still running when last read"] += 1
        elif int(state["bid"]) == 0:
            skipped["auction ended with no bids"] += 1
        else:
            rows.append({
                "number": n, "when": state["end"], "date": day(state["end"]),
                "venue": "auction_2026", "chain": "base",
                "contract": AUCTION_2026, "wei": int(state["bid"]), "currency": "ETH",
                "buyer": state["bidder"], "seller": TREASURY, "tx_hash": "", "bids": "",
                "source": "stored_values",
                "note": "" if state["settled"] else "auction over, not yet settled on chain",
            })
    return rows, skipped


# ---- resales in the main collection ---------------------------------------------------------------

def currency_of(token):
    token = token.lower()
    if token in (ZERO, WETH, BLUR_POOL):
        return {ZERO: "ETH", WETH: "WETH", BLUR_POOL: "ETH"}[token]
    if token == USDC:
        return "USDC"
    return token


def seaport_sales(log):
    """[(song, wei, currency, bundle size)] for the Song A Day tokens sold by one Seaport
    order, read from its OrderFulfilled event. An order either offers the token and asks for
    money (a listing) or offers money and asks for the token (an accepted offer)."""
    data = log["data"]
    base = 2
    offer_at = base + 2 * word(data, 2)
    cons_at = base + 2 * word(data, 3)
    n_offer = int(data[offer_at: offer_at + 64], 16)
    n_cons = int(data[cons_at: cons_at + 64], 16)

    def item(start, i, size):
        at = start + 64 + i * size * 64
        return [int(data[at + 64 * k: at + 64 * (k + 1)], 16) for k in range(size)]

    offer = [item(offer_at, i, 4) for i in range(n_offer)]
    cons = [item(cons_at, i, 5) for i in range(n_cons)]
    is_nft = lambda it: it[0] in (2, 3, 4, 5)
    is_money = lambda it: it[0] in (0, 1)
    addr = lambda n: "0x" + f"{n:040x}"
    offer_nfts = [it for it in offer if is_nft(it)]
    cons_nfts = [it for it in cons if is_nft(it)]
    if offer_nfts and not cons_nfts:      # a listing: money is in the consideration
        nfts, money = offer_nfts, [it for it in cons if is_money(it)]
    elif cons_nfts and not offer_nfts:    # an accepted offer: money is in the offer
        nfts, money = cons_nfts, [it for it in offer if is_money(it)]
    else:
        return []                         # NFT-for-NFT swaps and the like
    tokens = {addr(it[1]) for it in money}
    if len(tokens) != 1 or not money:
        return []
    total = sum(it[3] for it in money)
    ours = [it[2] for it in nfts if addr(it[1]) == SONGADAY]
    if not ours:
        return []
    return [(song, total // len(nfts), currency_of(tokens.pop()), len(nfts)) for song in ours]


def sale_events(tx):
    """Every sale of a Song A Day token recorded in one transaction's logs, in log order:
    [{number, wei, currency, market, bundle}]. Wyvern events don't name the token, so each is
    paired with the Song A Day transfers logged since the previous sale event."""
    found, since = [], []
    for log in tx["logs"]:
        topic, address = log["topics"][0], log["address"]
        if address == SONGADAY and topic == T_TRANSFER and len(log["topics"]) == 4:
            since.append(topic_int(log["topics"][3]))
        elif address in WYVERN and topic == T_WYVERN_MATCHED:
            price = word(log["data"], 2)
            for song in since:
                found.append({"number": song, "wei": price // len(since), "currency": None,
                              "market": "opensea_wyvern", "bundle": len(since)})
            since = []
        elif topic == T_SEAPORT_FULFILLED:
            for song, wei, currency, bundle in seaport_sales(log):
                found.append({"number": song, "wei": wei, "currency": currency,
                              "market": "opensea_seaport", "bundle": bundle})
        elif address == BLUR_V1 and topic == T_BLUR_MATCHED:
            sell = word(log["data"], 0) // 32
            w = words(log["data"])
            if "0x" + f"{w[sell + 3]:040x}" == SONGADAY:
                found.append({"number": w[sell + 4], "wei": w[sell + 7],
                              "currency": currency_of("0x" + f"{w[sell + 6]:040x}"),
                              "market": "blur", "bundle": 1})
        elif address == BLUR_V2 and topic in T_BLUR2:
            token_trader, collection_price = word(log["data"], 1), word(log["data"], 2)
            if "0x" + f"{collection_price & ((1 << 160) - 1):040x}" == SONGADAY:
                found.append({"number": token_trader >> 168,
                              "wei": (collection_price >> 160) & ((1 << 88) - 1),
                              "currency": "ETH", "market": "blur", "bundle": 1})
        elif address == LOOKSRARE and topic in T_LOOKS:
            _hash, _nonce, currency, collection, token, _amount, price = words(log["data"])[:7]
            if "0x" + f"{collection:040x}" == SONGADAY:
                found.append({"number": token, "wei": price,
                              "currency": currency_of("0x" + f"{currency:040x}"),
                              "market": "looksrare", "bundle": 1})
    # Seaport logs both sides of a matched pair (the listing and the mirror order that takes
    # it): the same song at the same price twice in one transaction is one sale.
    unique, seen = [], collections.Counter()
    moved = collections.Counter(topic_int(l["topics"][3]) for l in tx["logs"]
                                if l["address"] == SONGADAY and l["topics"][0] == T_TRANSFER
                                and len(l["topics"]) == 4)
    for sale in found:
        if seen[sale["number"]] >= max(1, moved[sale["number"]]):
            continue
        seen[sale["number"]] += 1
        unique.append(sale)
    return unique


def resales():
    transfers = songaday_transfers()
    moves = [t for t in transfers if topic_addr(t["topics"][1]) != ZERO
             and topic_addr(t["topics"][1]) not in VENUE_CONTRACTS
             and topic_addr(t["topics"][2]) not in VENUE_CONTRACTS]
    receipts = chain.receipts("ethereum", list(dict.fromkeys(t["transactionHash"] for t in moves)))
    by_tx = collections.defaultdict(list)
    for t in moves:
        by_tx[t["transactionHash"]].append(t)
    rows, skipped, unknown = [], collections.Counter(), collections.Counter()
    for tx_hash, tx_moves in by_tx.items():
        tx = receipts[tx_hash]
        sales = sale_events(tx)
        paid_weth = any(l["address"] == WETH and l["topics"][0] == T_TRANSFER for l in tx["logs"])
        per_song = collections.defaultdict(list)
        for t in tx_moves:
            per_song[topic_int(t["topics"][3])].append(t)
        used = collections.Counter()
        for sale in sales:
            hops = per_song.get(sale["number"])
            if not hops:
                continue
            # One sale of the song in this transaction: seller is where it started, buyer is
            # where it ended up (it may pass through a marketplace helper on the way). More
            # than one: pair the i-th sale with the i-th transfer.
            n_sales = sum(1 for s in sales if s["number"] == sale["number"])
            if n_sales == 1:
                seller, buyer = topic_addr(hops[0]["topics"][1]), topic_addr(hops[-1]["topics"][2])
            else:
                hop = hops[min(used[sale["number"]], len(hops) - 1)]
                seller, buyer = topic_addr(hop["topics"][1]), topic_addr(hop["topics"][2])
            used[sale["number"]] += 1
            currency = sale["currency"] or ("ETH" if tx["value"] else "WETH" if paid_weth else "ETH")
            rows.append({
                "number": sale["number"], "when": tx_moves[0]["timeStamp"],
                "date": day(tx_moves[0]["timeStamp"]), "venue": sale["market"], "chain": "ethereum", "contract": SONGADAY,
                "wei": sale["wei"], "currency": currency, "buyer": buyer, "seller": seller,
                "tx_hash": tx_hash, "bids": "", "source": "events",
                "note": "sold in a bundle; price split evenly" if sale["bundle"] > 1 else "",
            })
        for song in per_song:
            if not used[song]:
                direct = (tx["to"] in (SONGADAY, OPENSEA_TRANSFER_HELPER)
                          or tx["from"] in OURS or tx["to"] in OURS)
                if direct:
                    skipped["transfers with no sale event, sent directly (gifts, wallet moves, deliveries)"] += 1
                else:
                    skipped["transfers with no sale event, through another contract"] += 1
                    unknown[tx["to"]] += 1
    return rows, skipped, unknown


# ---- main ---------------------------------------------------------------------------------------

def last_song_number():
    with SONGS_CSV.open() as f:
        return max(int(row["number"]) for row in csv.DictReader(f))


def print_contracts():
    for venue, chain_name, address, years, songs, how, status in VENUES:
        print(f"{venue:20} {chain_name:11} {years:10} songs {songs:10} {status}")
        print(f"{'':20} {address}")
        print(f"{'':20} {how}")


def main():
    global REFRESH
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true", help="cache only, no network")
    parser.add_argument("--refresh", action="store_true",
                        help="also read events and auctions newer than the cache")
    parser.add_argument("--contracts", action="store_true", help="print the contract list")
    args = parser.parse_args()
    if args.contracts:
        print_contracts()
        return
    chain.OFFLINE = args.offline
    REFRESH = args.refresh and not args.offline
    last_song = last_song_number()

    rows, skipped, unknown = [], {}, collections.Counter()
    steps = [
        ("opensea_2021", opensea_2021),
        ("mint_2021", mint_2021),
        ("zora_2022", zora_2022),
        ("gbm_v1", lambda: gbm_events("gbm_v1", "ethereum", GBM_V1, 15_000_000)),
        ("gbm_v2", lambda: gbm_events("gbm_v2", "ethereum", GBM_V2, 15_000_000)),
        ("gbm_zora", lambda: gbm_events("gbm_zora", "zora", GBM_ZORA, 0)),
        ("gbm_base", lambda: gbm_base(last_song)),
        ("auction_2026", lambda: auction_2026(last_song)),
    ]
    try:
        for name, step in steps:
            print(f"{name} ...", flush=True)
            found, missed = step()
            rows += found
            skipped[name] = missed
        print("resales ...", flush=True)
        found, missed, unknown = resales()
        rows += found
        skipped["resales"] = missed
        prices = eth_usd_by_day()
    except chain.Offline as err:
        sys.exit(f"sales.py --offline: {err}. Run once without --offline.")

    # first sale or resale
    primary_first = lambda r: r["venue"] not in primary
    first_seen = set()
    primary = {"opensea_2021", "mint_2021", "zora_2022", "gbm_v1", "gbm_v2", "gbm_zora", "gbm_base",
               "auction_2026"}
    # In time order; at the same second (a song minted and resold in one block) the first
    # sale goes first.
    rows.sort(key=lambda r: (r["when"], primary_first(r), r["number"], r["tx_hash"]))
    for r in rows:
        from_us = r["venue"] in primary or r["seller"] in OURS
        r["kind"] = "first_sale" if from_us and r["number"] not in first_seen else "resale"
        if from_us and r["number"] in first_seen and not r["note"]:
            r["note"] = "sold again by Jonathan or the treasury"
        first_seen.add(r["number"])

    problems = []
    out = []
    for r in rows:
        if not 1 <= r["number"] <= last_song:
            problems.append(f"sale of song {r['number']}, which is not in songs.csv")
            continue
        rate = prices.get(r["date"])
        is_eth = r["currency"] in ("ETH", "WETH")
        if r["currency"] == "USDC":
            r["price"] = format(Decimal(r["wei"]) / Decimal(10 ** 6), "f").rstrip("0").rstrip(".")
            r["price_usd"], r["eth_usd"] = f"{float(r['price']):.2f}", ""
        else:
            r["price"] = eth(r["wei"])
            if is_eth and rate is None:
                problems.append(f"no ETH price for {r['date']}")
            r["eth_usd"] = f"{rate:.2f}" if is_eth and rate else ""
            r["price_usd"] = f"{float(Decimal(r['wei']) / Decimal(10 ** 18)) * rate:.2f}" \
                if is_eth and rate else ""
        out.append(r)
    if problems:
        sys.exit("sales.py: " + "; ".join(sorted(set(problems))[:10]))

    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(out)
    report(out, skipped, unknown, last_song)


def report(rows, skipped, unknown, last_song):
    first = [r for r in rows if r["kind"] == "first_sale"]
    again = [r for r in rows if r["kind"] == "resale"]
    eth_rows = lambda rs: [r for r in rs if r["currency"] in ("ETH", "WETH")]
    total = lambda rs: (sum(Decimal(r["price"]) for r in eth_rows(rs)),
                        sum(float(r["price_usd"] or 0) for r in rs))
    print(f"\nwrote {OUT_CSV.relative_to(ROOT)}: {len(rows)} sales "
          f"({len(first)} first sales, {len(again)} resales)")
    print(f"songs with a first sale: {len({r['number'] for r in first})} of {last_song}; "
          f"songs with any sale: {len({r['number'] for r in rows})}")
    print("\nfirst sales by venue        sales       ETH          USD   songs")
    for venue in dict.fromkeys(r["venue"] for r in first):
        rs = [r for r in first if r["venue"] == venue]
        e, u = total(rs)
        print(f"  {venue:22} {len(rs):7} {e:9.3f} {u:12,.0f}   "
              f"{min(r['number'] for r in rs)}-{max(r['number'] for r in rs)}")
    print("\nby year          first sales       ETH          USD     resales       ETH          USD")
    for year in sorted({r["date"][:4] for r in rows}):
        a = [r for r in first if r["date"].startswith(year)]
        b = [r for r in again if r["date"].startswith(year)]
        (ae, au), (be, bu) = total(a), total(b)
        print(f"  {year}           {len(a):7} {ae:9.3f} {au:12,.0f}     {len(b):7} {be:9.3f} {bu:12,.0f}")
    (ae, au), (be, bu) = total(first), total(again)
    print(f"  all            {len(first):7} {ae:9.3f} {au:12,.0f}     {len(again):7} {be:9.3f} {bu:12,.0f}")
    print("\nten highest sales (by ETH)")
    for r in sorted(eth_rows(rows), key=lambda r: -Decimal(r["price"]))[:10]:
        print(f"  #{r['number']:<5} {r['date']}  {Decimal(r['price']):8.3f} ETH  "
              f"${float(r['price_usd']):>10,.0f}  {r['kind']:10} {r['venue']}")
    print("\nten highest sales (by USD that day)")
    for r in sorted(rows, key=lambda r: -float(r["price_usd"] or 0))[:10]:
        print(f"  #{r['number']:<5} {r['date']}  {Decimal(r['price']):8.3f} {r['currency']:4} "
              f"${float(r['price_usd']):>10,.0f}  {r['kind']:10} {r['venue']}")
    print("\nnot written as sales")
    for name, counts in skipped.items():
        for why, n in counts.items():
            print(f"  {name:14} {n:6}  {why}")
    if unknown:
        print("  contracts those unrecognised transfers went through (transactions):")
        for address, n in unknown.most_common(8):
            print(f"    {n:5}  {address}")
    sold = {r["number"] for r in first}
    print("\nsongs with no first sale, by year of the song")
    with SONGS_CSV.open() as f:
        years = collections.defaultdict(lambda: [0, 0])
        for row in csv.DictReader(f):
            years[row["date"][:4]][0] += 1
            years[row["date"][:4]][1] += int(row["number"]) in sold
    for year, (songs, with_sale) in sorted(years.items()):
        print(f"  {year}: {with_sale:4} of {songs} sold, {songs - with_sale} not")


if __name__ == "__main__":
    main()
