"""
Quick BSC/Arbitrum fetch with smaller time ranges
"""
import asyncio
import httpx
import json
from datetime import datetime, timezone
from web3 import Web3
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("wBAN_quick")

SWAP_EVENT_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
OUTPUT_FILE = "wban_analytics_data.json"

CHAINS = {
    "bsc": {
        "name": "BSC",
        "lp_address": "0x351A295AfBAB020Bc7eedcB7fd5A823c01A95Fda",
        "rpc_urls": [
            "https://bsc-dataseed1.binance.org",
            "https://bsc-dataseed2.binance.org",
            "https://bsc.publicnode.com",
            "https://rpc.ankr.com/bsc",
        ],
        "block_time": 3,
        "wban_is_token0": True,
        "quote_token": "BUSD",
        "quote_decimals": 18,
    },
    "bsc_usdc": {
        "name": "BSC (USDC)",
        "lp_address": "0x76B1aB2f84bE3C4a103ef1d2C2a74145414FFA49",
        "rpc_urls": [
            "https://bsc-dataseed1.binance.org",
            "https://bsc-dataseed2.binance.org",
            "https://bsc.publicnode.com",
            "https://rpc.ankr.com/bsc",
        ],
        "block_time": 3,
        "wban_is_token0": False,
        "quote_token": "USDC",
        "quote_decimals": 18,
    },
    "arbitrum": {
        "name": "Arbitrum",
        "lp_address": "0xBD80923830B1B122dcE0C446b704621458329F1D",
        "rpc_urls": [
            "https://arb1.arbitrum.io/rpc",
            "https://arbitrum-one.publicnode.com",
            "https://rpc.ankr.com/arbitrum",
        ],
        "block_time": 0.25,
        "wban_is_token0": False,
        "quote_token": "WETH",
        "quote_decimals": 18,
    },
}

LP_ABI = [{"constant": True, "inputs": [], "name": "getReserves",
           "outputs": [{"name": "_reserve0", "type": "uint112"},
                       {"name": "_reserve1", "type": "uint112"},
                       {"name": "_blockTimestampLast", "type": "uint32"}],
           "stateMutability": "view", "type": "function"}]


def load_data():
    try:
        with open(OUTPUT_FILE, "r") as f:
            return json.load(f)
    except:
        return {"chains": {}, "totals": {"1_month": {}, "3_months": {}}}


def save_data(data):
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved to {OUTPUT_FILE}")


async def get_wban_price():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.coinex.com/v1/market/ticker?market=BANANOUSDT")
            if r.status_code == 200:
                return float(r.json()["data"]["ticker"]["last"])
    except:
        pass
    return 0.000481  # fallback


def get_web3(chain_id):
    for url in CHAINS[chain_id]["rpc_urls"]:
        try:
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 30}))
            if w3.is_connected():
                logger.info(f"{chain_id}: Connected to {url[:40]}")
                return w3
        except:
            continue
    return None


async def fetch_swaps(chain_id, w3, from_block, to_block, max_range=2000):
    """Fetch with smaller range for BSC"""
    config = CHAINS[chain_id]
    lp_address = Web3.to_checksum_address(config["lp_address"])
    all_events = []
    current = from_block

    logger.info(f"{chain_id}: Fetching {to_block - from_block:,} blocks")

    while current < to_block:
        end = min(current + max_range, to_block)
        try:
            logs = w3.eth.get_logs({
                "fromBlock": current,
                "toBlock": end,
                "address": lp_address,
                "topics": [SWAP_EVENT_TOPIC]
            })
            all_events.extend(logs)
            current = end + 1

            if len(all_events) % 50 == 0 and len(all_events) > 0:
                logger.info(f"{chain_id}: {len(all_events)} swaps so far")

            await asyncio.sleep(0.1)
        except Exception as e:
            if "limit" in str(e).lower() or "range" in str(e).lower():
                max_range = max(max_range // 2, 500)
                logger.info(f"{chain_id}: Reducing range to {max_range}")
            else:
                logger.warning(f"{chain_id}: Error at block {current}: {str(e)[:50]}")
                current = end + 1  # Skip problematic range
            await asyncio.sleep(0.5)

    return all_events


def parse_swap(log, wban_is_token0):
    try:
        data = log["data"].hex() if isinstance(log["data"], bytes) else log["data"]
        if data.startswith("0x"):
            data = data[2:]
        a0_in = int(data[0:64], 16)
        a1_in = int(data[64:128], 16)
        a0_out = int(data[128:192], 16)
        a1_out = int(data[192:256], 16)

        if wban_is_token0:
            return (a0_in + a0_out) / 10**18
        else:
            return (a1_in + a1_out) / 10**18
    except:
        return 0


async def analyze_chain(chain_id, price):
    config = CHAINS[chain_id]
    w3 = get_web3(chain_id)
    if not w3:
        return None

    current_block = w3.eth.block_number
    blocks_per_day = int(86400 / config["block_time"])

    # Use 1 month and 3 months
    blocks_1m = blocks_per_day * 30
    blocks_3m = blocks_per_day * 90

    from_1m = max(1, current_block - blocks_1m)
    from_3m = max(1, current_block - blocks_3m)

    # Get liquidity
    try:
        contract = w3.eth.contract(address=Web3.to_checksum_address(config["lp_address"]), abi=LP_ABI)
        reserves = contract.functions.getReserves().call()
        if config["wban_is_token0"]:
            wban = reserves[0] / 10**18
            quote = reserves[1] / 10**config["quote_decimals"]
        else:
            wban = reserves[1] / 10**18
            quote = reserves[0] / 10**config["quote_decimals"]
    except:
        wban, quote = None, None

    # Fetch swaps - try 3 months first
    logger.info(f"=== {config['name']}: Fetching 3 months of swaps ===")
    events_3m = await fetch_swaps(chain_id, w3, from_3m, current_block)
    events_1m = [e for e in events_3m if e["blockNumber"] >= from_1m]

    vol_1m = sum(parse_swap(e, config["wban_is_token0"]) for e in events_1m)
    vol_3m = sum(parse_swap(e, config["wban_is_token0"]) for e in events_3m)

    return {
        "name": config["name"],
        "lp_address": config["lp_address"],
        "current_block": current_block,
        "liquidity": {
            "wban": wban,
            "quote_token": config["quote_token"],
            "quote_amount": quote,
            "usd": wban * price * 2 if wban else None,
        },
        "1_month": {
            "swap_count": len(events_1m),
            "volume_wban": vol_1m,
            "volume_usd": vol_1m * price,
        },
        "3_months": {
            "swap_count": len(events_3m),
            "volume_wban": vol_3m,
            "volume_usd": vol_3m * price,
        },
    }


def recalc_totals(data):
    data["totals"] = {
        "1_month": {"swap_count": 0, "volume_wban": 0, "volume_usd": 0},
        "3_months": {"swap_count": 0, "volume_wban": 0, "volume_usd": 0},
    }
    for chain in data["chains"].values():
        data["totals"]["1_month"]["swap_count"] += chain["1_month"]["swap_count"]
        data["totals"]["1_month"]["volume_wban"] += chain["1_month"]["volume_wban"]
        data["totals"]["1_month"]["volume_usd"] += chain["1_month"]["volume_usd"] or 0
        data["totals"]["3_months"]["swap_count"] += chain["3_months"]["swap_count"]
        data["totals"]["3_months"]["volume_wban"] += chain["3_months"]["volume_wban"]
        data["totals"]["3_months"]["volume_usd"] += chain["3_months"]["volume_usd"] or 0


async def main():
    data = load_data()
    price = await get_wban_price()
    logger.info(f"wBAN price: ${price}")

    for chain_id in ["arbitrum", "bsc", "bsc_usdc"]:
        if chain_id in data.get("chains", {}):
            logger.info(f"Skipping {chain_id} - already have data")
            continue

        result = await analyze_chain(chain_id, price)
        if result:
            data["chains"][chain_id] = result
            data["generated_at"] = datetime.now(timezone.utc).isoformat()
            data["wban_price_usd"] = price
            recalc_totals(data)
            save_data(data)
            logger.info(f"Saved {chain_id}")

    print("\n=== RESULTS ===")
    for cid, c in data["chains"].items():
        print(f"{c['name']}: {c['1_month']['swap_count']} swaps (1m), {c['3_months']['swap_count']} swaps (3m)")


if __name__ == "__main__":
    asyncio.run(main())
