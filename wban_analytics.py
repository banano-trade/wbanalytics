"""
wBAN Analytics - Fetch historical swap data and liquidity across chains
Saves progress incrementally to avoid losing data
"""
import asyncio
import httpx
import json
import time
from datetime import datetime, timezone
from web3 import Web3
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("wBAN_analytics")

# Uniswap V2 Swap event signature
SWAP_EVENT_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"

OUTPUT_FILE = "wban_analytics_data.json"

# Chain configurations with LOTS of RPCs
CHAINS = {
    "ethereum": {
        "name": "Ethereum",
        "lp_address": "0x1f249F8b5a42aa78cc8a2b66EE0bb015468a5f43",
        "rpc_urls": [
            "https://eth.drpc.org",
            "https://eth-pokt.nodies.app",
            "https://eth.llamarpc.com",
            "https://ethereum-rpc.publicnode.com",
            "https://eth.meowrpc.com",
            "https://rpc.ankr.com/eth",
            "https://cloudflare-eth.com",
        ],
        "block_time": 12,
        "wban_is_token0": False,
        "quote_token": "WETH",
        "quote_decimals": 18,
    },
    "polygon": {
        "name": "Polygon",
        "lp_address": "0xb556feD3B348634a9A010374C406824Ae93F0CF8",
        "rpc_urls": [
            "https://polygon.drpc.org",
            "https://polygon.meowrpc.com",
            "https://polygon-bor.publicnode.com",
            "https://1rpc.io/matic",
            "https://polygon-rpc.com",
            "https://rpc.ankr.com/polygon",
        ],
        "block_time": 2,
        "wban_is_token0": False,
        "quote_token": "WETH",
        "quote_decimals": 18,
    },
    "bsc": {
        "name": "BSC",
        "lp_address": "0x351A295AfBAB020Bc7eedcB7fd5A823c01A95Fda",
        "rpc_urls": [
            "https://bsc.drpc.org",
            "https://bsc-pokt.nodies.app",
            "https://1rpc.io/bnb",
            "https://bsc.meowrpc.com",
            "https://bsc-dataseed4.bnbchain.org",
            "https://bsc-dataseed1.defibit.io",
            "https://bsc-dataseed2.ninicoin.io",
            "https://binance.llamarpc.com",
            "https://bsc.rpc.blxrbdn.com",
            "https://bsc-mainnet.nodereal.io/v1/64a9df0874fb4a93b9d0a3849de012d3",
            "https://rpc-bsc.48.club",
            "https://bsc.blockrazor.xyz",
            "https://bsc-dataseed1.binance.org",
            "https://bsc-dataseed2.binance.org",
            "https://bsc-dataseed3.binance.org",
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
            "https://bsc.drpc.org",
            "https://bsc-pokt.nodies.app",
            "https://1rpc.io/bnb",
            "https://bsc.meowrpc.com",
            "https://bsc-dataseed4.bnbchain.org",
            "https://bsc-dataseed1.defibit.io",
            "https://bsc-dataseed2.ninicoin.io",
            "https://binance.llamarpc.com",
            "https://bsc.rpc.blxrbdn.com",
            "https://bsc-mainnet.nodereal.io/v1/64a9df0874fb4a93b9d0a3849de012d3",
            "https://rpc-bsc.48.club",
            "https://bsc.blockrazor.xyz",
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
            "https://endpoints.omniatech.io/v1/arbitrum/one/public",
            "https://1rpc.io/arb",
            "https://arb1.arbitrum.io/rpc",
            "https://arbitrum.meowrpc.com",
            "https://arbitrum-one.publicnode.com",
            "https://rpc.tornadoeth.cash/arbitrum",
            "https://arb-pokt.nodies.app",
            "https://api.zan.top/node/v1/arb/one/public",
            "https://rpc.poolz.finance/arbitrum",
            "https://arb-one-mainnet.gateway.tatum.io",
            "https://arb1.lava.build",
            "https://rpc.ankr.com/arbitrum",
            "https://arbitrum.drpc.org",
        ],
        "block_time": 0.25,
        "wban_is_token0": False,
        "quote_token": "WETH",
        "quote_decimals": 18,
    },
}

LP_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


def load_existing_data():
    """Load existing analytics data if available"""
    try:
        with open(OUTPUT_FILE, "r") as f:
            data = json.load(f)
            logger.info(f"Loaded existing data with chains: {list(data.get('chains', {}).keys())}")
            return data
    except FileNotFoundError:
        logger.info("No existing data found, starting fresh")
        return None
    except Exception as e:
        logger.error(f"Error loading existing data: {e}")
        return None


def save_data(results):
    """Save results to file"""
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Data saved to {OUTPUT_FILE}")


class WBANAnalytics:
    def __init__(self):
        existing = load_existing_data()
        if existing:
            self.results = existing
        else:
            self.results = {
                "generated_at": None,
                "chains": {},
                "totals": {
                    "1_month": {"swap_count": 0, "volume_wban": 0, "volume_usd": 0},
                    "3_months": {"swap_count": 0, "volume_wban": 0, "volume_usd": 0},
                },
            }
        self.wban_price_usd = self.results.get("wban_price_usd")

    async def get_wban_price(self):
        """Fetch current wBAN price from CoinEx"""
        url = "https://api.coinex.com/v1/market/ticker?market=BANANOUSDT"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    self.wban_price_usd = float(data["data"]["ticker"]["last"])
                    return self.wban_price_usd
        except Exception as e:
            logger.error(f"Error fetching wBAN price: {e}")
        return self.wban_price_usd  # Return cached if available

    def get_web3_connection(self, rpc_url):
        """Get Web3 connection for a specific RPC"""
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 20}))
            if w3.is_connected():
                return w3
        except:
            pass
        return None

    def get_working_web3(self, chain_id):
        """Try all RPCs and return a working one"""
        config = CHAINS[chain_id]
        for rpc_url in config["rpc_urls"]:
            w3 = self.get_web3_connection(rpc_url)
            if w3:
                return w3, rpc_url
        return None, None

    async def get_liquidity(self, chain_id):
        """Get current liquidity for a chain"""
        config = CHAINS[chain_id]
        w3, _ = self.get_working_web3(chain_id)
        if not w3:
            return None, None

        try:
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(config["lp_address"]),
                abi=LP_ABI
            )
            reserves = contract.functions.getReserves().call()

            if config["wban_is_token0"]:
                wban_reserve = reserves[0] / 10**18
                quote_reserve = reserves[1] / 10**config["quote_decimals"]
            else:
                wban_reserve = reserves[1] / 10**18
                quote_reserve = reserves[0] / 10**config["quote_decimals"]

            return wban_reserve, quote_reserve
        except Exception as e:
            logger.error(f"Error getting liquidity for {chain_id}: {e}")
            return None, None

    async def fetch_swap_events(self, chain_id, from_block, to_block):
        """Fetch Swap events with aggressive retry and RPC switching"""
        config = CHAINS[chain_id]
        lp_address = Web3.to_checksum_address(config["lp_address"])

        # Start with reasonable range based on chain
        if chain_id == "arbitrum":
            max_range = 100000
        elif chain_id in ["polygon"]:
            max_range = 5000
        elif chain_id in ["bsc", "bsc_usdc"]:
            max_range = 5000
        else:
            max_range = 5000

        all_events = []
        current_from = from_block
        total_blocks = to_block - from_block
        rpc_index = 0
        fail_count = 0
        range_fail_count = 0

        logger.info(f"Fetching swaps for {chain_id}: {total_blocks:,} blocks")

        # Get initial connection
        w3, current_rpc = self.get_working_web3(chain_id)
        if not w3:
            logger.error(f"No working RPC for {chain_id}")
            return []

        while current_from < to_block:
            current_to = min(current_from + max_range, to_block)

            try:
                logs = w3.eth.get_logs({
                    "fromBlock": current_from,
                    "toBlock": current_to,
                    "address": lp_address,
                    "topics": [SWAP_EVENT_TOPIC]
                })
                all_events.extend(logs)
                fail_count = 0
                range_fail_count = 0

                # Progress
                progress = ((current_to - from_block) / total_blocks) * 100
                if len(all_events) % 100 < len(logs) or progress % 10 < (max_range / total_blocks * 100):
                    logger.info(f"{chain_id}: {progress:.1f}% - {len(all_events)} swaps")

                current_from = current_to + 1
                await asyncio.sleep(0.05)

            except Exception as e:
                error_msg = str(e).lower()
                fail_count += 1

                # Check if it's a range/limit issue
                if any(x in error_msg for x in ["limit", "range", "exceeded", "too many", "timeout"]):
                    range_fail_count += 1
                    if range_fail_count >= 3 and max_range > 500:
                        max_range = max(max_range // 2, 500)
                        logger.info(f"{chain_id}: Reducing range to {max_range}")
                        range_fail_count = 0
                        continue
                    elif max_range <= 500:
                        # Range is already minimal, switch RPC
                        pass

                # Switch RPC after failures
                if fail_count >= 2:
                    rpc_index += 1
                    if rpc_index < len(config["rpc_urls"]):
                        new_rpc = config["rpc_urls"][rpc_index]
                        logger.info(f"{chain_id}: Switching to RPC #{rpc_index + 1}: {new_rpc[:40]}...")
                        w3 = self.get_web3_connection(new_rpc)
                        if w3:
                            fail_count = 0
                            max_range = max(max_range, 2000)  # Reset range a bit
                            continue
                    else:
                        # Tried all RPCs, cycle back
                        rpc_index = 0
                        logger.warning(f"{chain_id}: Cycling through RPCs again")

                        # If we've really struggled, just move on
                        if fail_count >= 10:
                            logger.error(f"{chain_id}: Too many failures, skipping block range")
                            current_from = current_to + 1
                            fail_count = 0

                await asyncio.sleep(1)

        logger.info(f"{chain_id}: Done - {len(all_events)} total swaps")
        return all_events

    def parse_swap_event(self, log, wban_is_token0):
        """Parse a Swap event to extract wBAN volume"""
        try:
            data = log["data"].hex() if isinstance(log["data"], bytes) else log["data"]
            if data.startswith("0x"):
                data = data[2:]

            amount0_in = int(data[0:64], 16)
            amount1_in = int(data[64:128], 16)
            amount0_out = int(data[128:192], 16)
            amount1_out = int(data[192:256], 16)

            if wban_is_token0:
                wban_in = amount0_in / 10**18
                wban_out = amount0_out / 10**18
            else:
                wban_in = amount1_in / 10**18
                wban_out = amount1_out / 10**18

            return wban_in + wban_out
        except Exception as e:
            return 0

    async def analyze_chain(self, chain_id):
        """Analyze swap activity for a single chain"""
        config = CHAINS[chain_id]
        logger.info(f"=== Analyzing {config['name']} ===")

        w3, _ = self.get_working_web3(chain_id)
        if not w3:
            logger.error(f"Could not connect to {chain_id}")
            return None

        current_block = w3.eth.block_number

        # Calculate block ranges
        blocks_per_day = int(86400 / config["block_time"])
        blocks_1_month = blocks_per_day * 30
        blocks_3_months = blocks_per_day * 90

        from_block_1m = max(1, current_block - blocks_1_month)
        from_block_3m = max(1, current_block - blocks_3_months)

        # Get liquidity
        wban_reserve, quote_reserve = await self.get_liquidity(chain_id)

        # Fetch swap events
        events_3m = await self.fetch_swap_events(chain_id, from_block_3m, current_block)
        events_1m = [e for e in events_3m if e["blockNumber"] >= from_block_1m]

        # Calculate volumes
        volume_1m = sum(self.parse_swap_event(e, config["wban_is_token0"]) for e in events_1m)
        volume_3m = sum(self.parse_swap_event(e, config["wban_is_token0"]) for e in events_3m)

        # USD liquidity
        liquidity_usd = wban_reserve * self.wban_price_usd * 2 if wban_reserve and self.wban_price_usd else None

        return {
            "name": config["name"],
            "lp_address": config["lp_address"],
            "current_block": current_block,
            "liquidity": {
                "wban": wban_reserve,
                "quote_token": config["quote_token"],
                "quote_amount": quote_reserve,
                "usd": liquidity_usd,
            },
            "1_month": {
                "swap_count": len(events_1m),
                "volume_wban": volume_1m,
                "volume_usd": volume_1m * self.wban_price_usd if self.wban_price_usd else None,
            },
            "3_months": {
                "swap_count": len(events_3m),
                "volume_wban": volume_3m,
                "volume_usd": volume_3m * self.wban_price_usd if self.wban_price_usd else None,
            },
        }

    def recalculate_totals(self):
        """Recalculate totals from chain data"""
        self.results["totals"] = {
            "1_month": {"swap_count": 0, "volume_wban": 0, "volume_usd": 0},
            "3_months": {"swap_count": 0, "volume_wban": 0, "volume_usd": 0},
        }
        for chain_data in self.results["chains"].values():
            self.results["totals"]["1_month"]["swap_count"] += chain_data["1_month"]["swap_count"]
            self.results["totals"]["1_month"]["volume_wban"] += chain_data["1_month"]["volume_wban"]
            if chain_data["1_month"]["volume_usd"]:
                self.results["totals"]["1_month"]["volume_usd"] += chain_data["1_month"]["volume_usd"]

            self.results["totals"]["3_months"]["swap_count"] += chain_data["3_months"]["swap_count"]
            self.results["totals"]["3_months"]["volume_wban"] += chain_data["3_months"]["volume_wban"]
            if chain_data["3_months"]["volume_usd"]:
                self.results["totals"]["3_months"]["volume_usd"] += chain_data["3_months"]["volume_usd"]

    async def run_analysis(self, skip_existing=True):
        """Run analysis, optionally skipping chains we already have"""
        logger.info("Starting wBAN analytics...")

        # Get price
        await self.get_wban_price()
        if self.wban_price_usd:
            logger.info(f"wBAN price: ${self.wban_price_usd:.6f}")

        # Analyze each chain
        for chain_id in CHAINS:
            # Skip if we already have data for this chain
            if skip_existing and chain_id in self.results.get("chains", {}):
                logger.info(f"Skipping {chain_id} - already have data")
                continue

            try:
                result = await self.analyze_chain(chain_id)
                if result:
                    self.results["chains"][chain_id] = result

                    # Save after each chain!
                    self.results["generated_at"] = datetime.now(timezone.utc).isoformat()
                    self.results["wban_price_usd"] = self.wban_price_usd
                    self.recalculate_totals()
                    save_data(self.results)
                    logger.info(f"Saved data after completing {chain_id}")

            except Exception as e:
                logger.error(f"Error analyzing {chain_id}: {e}")

        self.print_summary()
        return self.results

    def print_summary(self):
        """Print summary"""
        print("\n" + "="*60)
        print("wBAN ANALYTICS SUMMARY")
        print("="*60)

        if self.wban_price_usd:
            print(f"\nwBAN Price: ${self.wban_price_usd:.6f}")

        print("\n--- LIQUIDITY ---")
        for chain_id, data in sorted(self.results["chains"].items(),
                                      key=lambda x: x[1]["liquidity"]["usd"] or 0, reverse=True):
            usd = data["liquidity"]["usd"]
            print(f"  {data['name']}: ${usd:,.2f}" if usd else f"  {data['name']}: N/A")

        print("\n--- 1 MONTH ---")
        for chain_id, data in sorted(self.results["chains"].items(),
                                      key=lambda x: x[1]["1_month"]["swap_count"], reverse=True):
            print(f"  {data['name']}: {data['1_month']['swap_count']} swaps, "
                  f"{data['1_month']['volume_wban']:,.0f} wBAN")

        print(f"\n  TOTAL: {self.results['totals']['1_month']['swap_count']} swaps")

        print("\n--- 3 MONTHS ---")
        for chain_id, data in sorted(self.results["chains"].items(),
                                      key=lambda x: x[1]["3_months"]["swap_count"], reverse=True):
            print(f"  {data['name']}: {data['3_months']['swap_count']} swaps, "
                  f"{data['3_months']['volume_wban']:,.0f} wBAN")

        print(f"\n  TOTAL: {self.results['totals']['3_months']['swap_count']} swaps")
        print("="*60)


async def main():
    analytics = WBANAnalytics()
    await analytics.run_analysis(skip_existing=True)


if __name__ == "__main__":
    asyncio.run(main())
