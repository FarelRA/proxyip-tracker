#! /usr/bin/env python3
"""
Cloudflare Proxy IP Discovery

Discovers Cloudflare proxy IPs within Oracle Cloud infrastructure by:
1. Fetching Oracle Cloud public IP CIDR ranges (IPv4 and IPv6)
2. Connecting to each IP on port 443 with TLS SNI set to speed.cloudflare.com
3. Checking if the response comes from Cloudflare's edge

Scans ALL IPs in every CIDR range with no limits, using asyncio for maximum parallelism.
"""

import asyncio
import ssl
import logging
import configparser
import ipaddress
from typing import List, Set

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

ORACLE_IP_RANGES_URL = "https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json"
CLOUDFLARE_HOST = "speed.cloudflare.com"
CLOUDFLARE_PORT = 443
TIMEOUT = 3
MAX_CONCURRENT = 2000
PROGRESS_INTERVAL = 50000

context = ssl.create_default_context()
context.check_hostname = True


def fetch_oracle_cidrs(url: str = ORACLE_IP_RANGES_URL) -> List[str]:
    """Fetch OCI public CIDR ranges (regions only, not oracle-services)."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise SystemExit(f"Failed to fetch Oracle IP ranges: {e}")

    cidrs: Set[str] = set()
    for region in data.get("regions", []):
        for entry in region.get("cidrs", []):
            cidr = entry.get("cidr")
            if cidr:
                cidrs.add(cidr)

    return sorted(cidrs)


async def scan_proxy(ip: str) -> bool:
    """
    Connect to IP:443 with TLS SNI=CLOUDFLARE_HOST, send /cdn-cgi/trace,
    check if response contains 'colo=' (Cloudflare proxy indicator).
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, CLOUDFLARE_PORT, ssl=context,
                                    server_hostname=CLOUDFLARE_HOST),
            timeout=TIMEOUT
        )
        req = (
            f"GET /cdn-cgi/trace HTTP/1.1\r\n"
            f"Host: {CLOUDFLARE_HOST}\r\n"
            f"Connection: close\r\n\r\n"
        )
        writer.write(req.encode())
        await writer.drain()

        data = b""
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=TIMEOUT)
            if not chunk:
                break
            data += chunk

        writer.close()
        await writer.wait_closed()

        return b"colo=" in data

    except (asyncio.TimeoutError, ConnectionRefusedError, ConnectionResetError,
            ssl.SSLError, OSError, ValueError):
        return False


async def scan_all(cidrs: List[str]) -> List[str]:
    """
    Scan ALL IPs in all CIDRs using asyncio with a semaphore cap.
    Every IP competes fairly for a concurrency slot — no CIDR monopolizes.
    """
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    results: List[str] = []
    scanned = 0
    active_tasks: Set[asyncio.Task] = set()

    async def scan_one(ip_str: str) -> None:
        nonlocal scanned
        try:
            if await scan_proxy(ip_str):
                results.append(ip_str)
        finally:
            sem.release()
            scanned += 1
            if scanned % PROGRESS_INTERVAL == 0:
                logging.info(f"Scanned {scanned:,} IPs, found {len(results)} proxies")

    total_addresses = 0
    for cidr in cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            total_addresses += network.num_addresses
        except (ValueError, OverflowError):
            pass

    logging.info(f"Total addresses across all CIDRs: {total_addresses:,}")

    for cidr in cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except (ValueError, OverflowError) as e:
            logging.warning(f"Skipping invalid CIDR {cidr}: {e}")
            continue

        logging.info(f"Scanning {cidr} ({network.num_addresses:,} addresses)")
        for ip in network.hosts():
            await sem.acquire()
            task = asyncio.create_task(scan_one(str(ip)))
            active_tasks.add(task)
            task.add_done_callback(active_tasks.discard)

    # Wait for remaining in-flight tasks
    if active_tasks:
        await asyncio.wait(active_tasks)

    logging.info(f"Total scanned: {scanned:,} IPs, found {len(results)} proxies")
    return results


def main():
    config = configparser.ConfigParser()
    config.read("config.ini")

    oracle_url = config.get('getIPs', 'url', fallback=ORACLE_IP_RANGES_URL)
    output_file = config.get('getIPs', 'output_file', fallback='result/ips.txt')

    logging.info(f"Fetching Oracle Cloud IP ranges from {oracle_url}")
    cidrs = fetch_oracle_cidrs(oracle_url)
    logging.info(f"Found {len(cidrs)} CIDR ranges")

    proxy_ips = asyncio.run(scan_all(cidrs))
    proxy_ips.sort()

    with open(output_file, 'w') as f:
        f.write("\n".join(proxy_ips) + ("\n" if proxy_ips else ""))
    logging.info(f"Saved {len(proxy_ips)} IPs to {output_file}")


if __name__ == "__main__":
    main()
