#! /usr/bin/env python3
"""
Cloudflare Proxy IP Discovery

Discovers Cloudflare proxy IPs within Oracle Cloud infrastructure by:
1. Fetching Oracle Cloud public IP CIDR ranges (IPv4 and IPv6)
2. Connecting to each IP on port 443 with TLS SNI set to speed.cloudflare.com
3. Checking if the response comes from Cloudflare's edge

Scans ALL IPs in every CIDR range with no limits, using asyncio for maximum parallelism.
Outputs a CSV with IP, colo code, and region name.
"""

import asyncio
import csv
import os
import ssl
import logging
import configparser
import ipaddress
from io import StringIO
from typing import List, Dict, Set, Tuple, Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

ORACLE_IP_RANGES_URL = "https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json"
CLOUDFLARE_HOST = "speed.cloudflare.com"
CLOUDFLARE_PORT = 443
TIMEOUT = 1
MAX_CONCURRENT = 2000
PROGRESS_INTERVAL = 50000
COLO_CSV_URL = "https://raw.githubusercontent.com/Netrvin/cloudflare-colo-list/refs/heads/main/DC-Colos.csv"

context = ssl.create_default_context()
context.check_hostname = True


def fetch_oracle_cidrs(url: str = ORACLE_IP_RANGES_URL) -> List[str]:
    """Fetch OCI CIDR ranges (only CIDRs tagged 'OCI')."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise SystemExit(f"Failed to fetch Oracle IP ranges: {e}")

    cidrs: Set[str] = set()
    for region in data.get("regions", []):
        for entry in region.get("cidrs", []):
            tags = entry.get("tags", [])
            if "OCI" in tags:
                cidr = entry.get("cidr")
                if cidr:
                    cidrs.add(cidr)

    return sorted(cidrs)


def fetch_cloudflare_colo_data() -> List[Dict[str, str]]:
    """Fetch Cloudflare colo data from a remote CSV."""
    try:
        response = requests.get(COLO_CSV_URL, timeout=4)
        response.raise_for_status()
        return list(csv.DictReader(StringIO(response.text)))
    except requests.RequestException as e:
        logging.error(f"Error fetching Cloudflare colo data: {e}")
        return []


def get_region_from_colo(colo: str, colo_data: List[Dict[str, str]]) -> str:
    """Find region for a given colo code."""
    for row in colo_data:
        if row.get('colo') == colo:
            return row.get('region', 'Unknown').replace(" ", "_")
    return "Unknown"


async def scan_proxy(ip: str) -> Optional[str]:
    """
    Connect to IP:443 with TLS SNI=CLOUDFLARE_HOST, send /cdn-cgi/trace,
    return colo code if Cloudflare proxy, else None.
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

        header_end = data.find(b"\r\n\r\n")
        if header_end == -1:
            return None
        body = data[header_end + 4:]
        for line in body.decode(errors='replace').splitlines():
            if line.startswith("colo="):
                return line.split("=")[1]
        return None

    except (asyncio.TimeoutError, ConnectionRefusedError, ConnectionResetError,
            ssl.SSLError, OSError, ValueError):
        return None


async def scan_all(cidrs: List[str], colo_data: List[Dict[str, str]]) -> List[Tuple[str, str, str]]:
    """
    Scan ALL IPs in all CIDRs using asyncio with a semaphore cap.
    Returns list of (ip, colo, region) tuples.
    """
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    results: List[Tuple[str, str, str]] = []
    scanned = 0
    active_tasks: Set[asyncio.Task] = set()

    async def scan_one(ip_str: str) -> None:
        nonlocal scanned
        try:
            colo = await scan_proxy(ip_str)
            if colo:
                region = get_region_from_colo(colo, colo_data)
                results.append((ip_str, colo, region))
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

    if active_tasks:
        await asyncio.wait(active_tasks)

    logging.info(f"Total scanned: {scanned:,} IPs, found {len(results)} proxies")
    return results


def main():
    config = configparser.ConfigParser()
    config.read("config.ini")

    oracle_url = config.get('getIPs', 'url', fallback=ORACLE_IP_RANGES_URL)
    output_file = config.get('getIPs', 'output_file', fallback='result/ips.csv')

    logging.info(f"Fetching Cloudflare colo data from {COLO_CSV_URL}")
    colo_data = fetch_cloudflare_colo_data()
    if not colo_data:
        raise RuntimeError("Failed to fetch Cloudflare colo data.")

    logging.info(f"Fetching Oracle Cloud IP ranges from {oracle_url}")
    cidrs = fetch_oracle_cidrs(oracle_url)
    logging.info(f"Found {len(cidrs)} CIDR ranges")

    results = asyncio.run(scan_all(cidrs, colo_data))
    results.sort(key=lambda x: x[0])

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['IP', 'Colo', 'Region'])
        writer.writerows(results)
    logging.info(f"Saved {len(results)} IPs to {output_file}")


if __name__ == "__main__":
    main()
