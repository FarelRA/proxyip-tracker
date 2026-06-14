#!/usr/bin/env python3
"""
Cloudflare IP Performance Tester

Tests Cloudflare proxy IP addresses for performance metrics
including ping, upload, and download speeds across different regions.
Uses socket-level connections for real proxy testing (IPv4 and IPv6).
"""

import os
import ssl
import csv
import time
import asyncio
import logging
import configparser
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Network ---
# Target hostname for TLS SNI and HTTP Host header
CLOUDFLARE_HOST = "speed.cloudflare.com"
CLOUDFLARE_PORT = 443
# TCP socket read buffer size
READ_BUFFER = 4096

# --- HTTP ---
# Sentinel to locate the end of HTTP headers in raw responses
HEADER_TERMINATOR = b"\r\n\r\n"
# Offset past HEADER_TERMINATOR to reach response body
HEADER_OFFSET = 4
# Expected HTTP status for successful requests
EXPECTED_STATUS = 200
HTTP_GET = "GET"
HTTP_POST = "POST"

# --- Endpoints ---
PATH_TRACE = "/cdn-cgi/trace"
PATH_DOWNLOAD = "/__down?bytes={}"
PATH_UPLOAD = "/__up"

# --- Speed calculation ---
BITS_PER_BYTE = 8
BYTES_PER_KB = 1024
BITS_TO_MBPS = 1_000_000
SPEED_ROUND = 2
# Milliseconds per second (for ping RTT conversion)
MS_CONVERSION = 1000
# Sentinel value returned when ping fails
PING_FAIL = -1

# --- Multipart ---
# Boundary prefix for multipart upload requests
BOUNDARY_PREFIX = "----WebKitFormBoundary"
# Random bytes appended to boundary for uniqueness
BOUNDARY_BYTES = 16

# --- CSV ---
# Output CSV column headers
CSV_HEADERS = ["IP", "Ping (ms)", "Upload (Mbps)", "Download (Mbps)"]

# --- Config keys ---
CFG_SPEED = "cfSpeedTest"
KEY_FILE_IPS = "file_ips"
KEY_MAX_IPS = "max_ips"
KEY_MAX_PING = "max_ping"
KEY_TEST_SIZE = "test_size"
KEY_MIN_DOWNLOAD = "min_download_speed"
KEY_MIN_UPLOAD = "min_upload_speed"
KEY_OUTPUT = "output_file"
KEY_TIMEOUT = "timeout"
KEY_PING_WORKERS = "ping_workers"

# --- Config defaults ---
# Used as fallbacks when config.ini keys are missing
DEFAULT_MAX_IPS = 10
DEFAULT_MAX_PING = 100
DEFAULT_TEST_SIZE = 1024
DEFAULT_MIN_DOWNLOAD = 5.0
DEFAULT_MIN_UPLOAD = 2.0
DEFAULT_OUTPUT_FILE = "ip_performance.csv"
DEFAULT_FILE_IPS = "ips.csv"
DEFAULT_TIMEOUT = 4
DEFAULT_PING_WORKERS = 20

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = True


def _run(coro):
    """
    Execute a coroutine in the current thread's event loop.

    Creates a fresh event loop per call and closes it immediately after
    to avoid Python 3.14+ cleanup warnings on garbage collection.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


@dataclass
class IPPerformanceMetrics:
    """Container for a single IP's speed test results."""
    ip: str
    ping: int
    upload_speed: float
    download_speed: float

    def to_csv_row(self) -> List[str]:
        """Format metrics as a CSV-ready list matching CSV_HEADERS order."""
        return [
            self.ip,
            str(self.ping),
            f"{self.upload_speed:.2f}",
            f"{self.download_speed:.2f}"
        ]


class CloudflareIPTester:
    """
    Main class for testing Cloudflare IP performance.

    Uses raw TLS socket connections through each target IP to measure
    real proxy performance (not just ICMP ping).
    """

    def __init__(self, config_path: str = "config.ini"):
        """Load configuration from config.ini, applying defaults for any missing keys."""
        self.config = configparser.ConfigParser()
        self.config.read(config_path)

        self.max_ips = self._get_config_int(CFG_SPEED, KEY_MAX_IPS, DEFAULT_MAX_IPS)
        self.max_ping = self._get_config_int(CFG_SPEED, KEY_MAX_PING, DEFAULT_MAX_PING)
        self.test_size = self._get_config_int(CFG_SPEED, KEY_TEST_SIZE, DEFAULT_TEST_SIZE)
        self.min_download_speed = self._get_config_float(CFG_SPEED, KEY_MIN_DOWNLOAD, DEFAULT_MIN_DOWNLOAD)
        self.min_upload_speed = self._get_config_float(CFG_SPEED, KEY_MIN_UPLOAD, DEFAULT_MIN_UPLOAD)
        self.output_file = self._get_config_str(CFG_SPEED, KEY_OUTPUT, DEFAULT_OUTPUT_FILE)
        self.ip_file = self._get_config_str(CFG_SPEED, KEY_FILE_IPS, DEFAULT_FILE_IPS)
        self.timeout = self._get_config_int(CFG_SPEED, KEY_TIMEOUT, DEFAULT_TIMEOUT)
        self.ping_workers = self._get_config_int(CFG_SPEED, KEY_PING_WORKERS, DEFAULT_PING_WORKERS)

    def _get_config_int(self, section: str, key: str, default: int) -> int:
        try:
            return self.config.getint(section, key)
        except (configparser.NoOptionError, ValueError):
            logging.warning(f"Using default value {default} for {key}")
            return default

    def _get_config_float(self, section: str, key: str, default: float) -> float:
        try:
            return self.config.getfloat(section, key)
        except (configparser.NoOptionError, ValueError):
            logging.warning(f"Using default value {default} for {key}")
            return default

    def _get_config_str(self, section: str, key: str, default: str) -> str:
        try:
            return self.config.get(section, key)
        except configparser.NoOptionError:
            logging.warning(f"Using default value {default} for {key}")
            return default

    @staticmethod
    def read_ips(file_path: str) -> Dict[str, List[str]]:
        """
        Read the IP CSV file and group IPs by region.

        Expects a CSV with columns 'IP' and 'Region' (produced by getIPs.py).
        Returns a dict mapping region names to lists of IP addresses.
        """
        try:
            region_ips: Dict[str, List[str]] = {}
            with open(file_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    region = row['Region'].strip()
                    ip = row['IP'].strip()
                    region_ips.setdefault(region, []).append(ip)
            if not region_ips:
                raise ValueError("No IP addresses found in the CSV")
            return region_ips
        except FileNotFoundError:
            raise FileNotFoundError(f"IP file not found: {file_path}")
        except Exception as e:
            raise FileNotFoundError(f"Error reading IP file: {e}")

    async def _socket_request(self, ip: str, path: str, method: str = HTTP_GET,
                               body: Optional[bytes] = None) -> Tuple[int, bytes]:
        """
        Make a raw HTTP request through a specific proxy IP.

        Opens a TLS socket to the target IP with SNI set to speed.cloudflare.com,
        sends an HTTP request, and parses the response. Returns (status_code, body).

        This is the core method that allows testing through the proxy rather than
        connecting directly to Cloudflare.
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, CLOUDFLARE_PORT, ssl=ssl_context,
                                        server_hostname=CLOUDFLARE_HOST),
                timeout=self.timeout
            )

            if method == HTTP_GET:
                req = (
                    f"GET {path} HTTP/1.1\r\n"
                    f"Host: {CLOUDFLARE_HOST}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()
            elif method == HTTP_POST:
                req = (
                    f"POST {path} HTTP/1.1\r\n"
                    f"Host: {CLOUDFLARE_HOST}\r\n"
                    f"Content-Type: multipart/form-data\r\n"
                    f"Content-Length: {len(body) if body else 0}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()
                if body:
                    req += body

            writer.write(req)
            await writer.drain()

            # Read entire response
            raw = b""
            while True:
                chunk = await asyncio.wait_for(reader.read(READ_BUFFER), timeout=self.timeout)
                if not chunk:
                    break
                raw += chunk

            writer.close()
            await writer.wait_closed()

            # Parse HTTP response: split headers from body
            header_end = raw.find(HEADER_TERMINATOR)
            if header_end == -1:
                return 0, raw

            status_line = raw[:raw.find(b"\r\n")].decode(errors='replace')
            status_code = 0
            if status_line.startswith("HTTP/"):
                try:
                    status_code = int(status_line.split(" ")[1])
                except (IndexError, ValueError):
                    pass

            return status_code, raw[header_end + HEADER_OFFSET:]

        except (asyncio.TimeoutError, ConnectionRefusedError, ConnectionResetError,
                ssl.SSLError, OSError, ValueError):
            return 0, b""

    def get_ping(self, ip: str) -> int:
        """
        Measure round-trip time through the proxy IP.

        Sends a GET /cdn-cgi/trace and measures the elapsed time until
        a successful 200 response. Returns the RTT in milliseconds,
        or PING_FAIL (-1) on failure.
        """
        start = time.time()
        status, _ = _run(self._socket_request(ip, PATH_TRACE))
        if status == EXPECTED_STATUS:
            rtt = int((time.time() - start) * MS_CONVERSION)
            logging.info(f"Ping for {ip}: {rtt} ms")
            return rtt
        return PING_FAIL

    def get_download_speed(self, ip: str) -> float:
        """
        Test download speed through the proxy IP.

        Requests test_size KB of data from Cloudflare's /__down endpoint.
        Calculates throughput in Mbps based on response size and elapsed time.
        """
        path = PATH_DOWNLOAD.format(self.test_size * BYTES_PER_KB)

        start = time.time()
        status, body = _run(self._socket_request(ip, path))
        if status != EXPECTED_STATUS or not body:
            return 0.0

        elapsed = time.time() - start
        if elapsed <= 0:
            return 0.0

        speed = round(len(body) * BITS_PER_BYTE / elapsed / BITS_TO_MBPS, SPEED_ROUND)
        logging.info(f"Download speed for {ip}: {speed} Mbps")
        return speed

    def get_upload_speed(self, ip: str) -> float:
        """
        Test upload speed through the proxy IP.

        Sends test_size KB of null bytes as a multipart/form-data POST
        to Cloudflare's /__up endpoint. Calculates throughput in Mbps
        based on upload size and elapsed time.
        """
        upload_size = int(self.test_size * BYTES_PER_KB)
        body = b"\x00" * upload_size
        boundary = BOUNDARY_PREFIX + os.urandom(BOUNDARY_BYTES).hex()
        payload = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="sample.bin"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + body + f"\r\n--{boundary}--\r\n".encode()

        start = time.time()
        status, response_body = _run(
            self._socket_request_raw(ip, PATH_UPLOAD, payload, boundary)
        )
        if status == 0:
            return 0.0

        elapsed = time.time() - start
        if elapsed <= 0:
            return 0.0

        speed = round(upload_size * BITS_PER_BYTE / elapsed / BITS_TO_MBPS, SPEED_ROUND)
        logging.info(f"Upload speed for {ip}: {speed} Mbps")
        return speed

    async def _socket_request_raw(self, ip: str, path: str, body: bytes,
                                    boundary: str) -> Tuple[int, bytes]:
        """
        Like _socket_request but tailored for raw multipart POST without
        the Content-Type needing to be rebuilt from the body.

        Used by get_upload_speed to send a pre-built multipart payload
        with a specific boundary string.
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, CLOUDFLARE_PORT, ssl=ssl_context,
                                        server_hostname=CLOUDFLARE_HOST),
                timeout=self.timeout
            )

            req = (
                f"POST {path} HTTP/1.1\r\n"
                f"Host: {CLOUDFLARE_HOST}\r\n"
                f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode() + body

            writer.write(req)
            await writer.drain()

            raw = b""
            while True:
                chunk = await asyncio.wait_for(reader.read(READ_BUFFER), timeout=self.timeout)
                if not chunk:
                    break
                raw += chunk

            writer.close()
            await writer.wait_closed()

            header_end = raw.find(HEADER_TERMINATOR)
            if header_end == -1:
                return 0, raw

            status_line = raw[:raw.find(b"\r\n")].decode(errors='replace')
            status_code = 0
            if status_line.startswith("HTTP/"):
                try:
                    status_code = int(status_line.split(" ")[1])
                except (IndexError, ValueError):
                    pass

            return status_code, raw[header_end + HEADER_OFFSET:]

        except (asyncio.TimeoutError, ConnectionRefusedError, ConnectionResetError,
                ssl.SSLError, OSError, ValueError):
            return 0, b""

    def filter_ips_by_ping(self, ip_list: List[str]) -> List[Tuple[str, int]]:
        """
        Ping a list of IPs in parallel and return those within max_ping.

        Uses a thread pool to test multiple IPs concurrently (each thread
        runs its own asyncio event loop). Results are sorted by ping time
        and capped to max_ips.
        """
        def ping_ip(ip):
            return ip, self.get_ping(ip)

        ip_ping_results = []
        with ThreadPoolExecutor(max_workers=self.ping_workers) as executor:
            future_to_ip = {executor.submit(ping_ip, ip): ip for ip in ip_list}
            for future in as_completed(future_to_ip):
                try:
                    ip, ping_time = future.result()
                    if ping_time > PING_FAIL and ping_time <= self.max_ping:
                        ip_ping_results.append((ip, ping_time))
                except Exception as e:
                    logging.error(f"Error pinging IP {future_to_ip[future]}: {e}")

        ip_ping_results.sort(key=lambda x: x[1])
        return ip_ping_results[:self.max_ips]

    def run_tests(self) -> List[IPPerformanceMetrics]:
        """
        Run the full test pipeline: read IPs, ping, speed test.

        For each region: pings all IPs, keeps the fastest within max_ping,
        then tests download and upload speeds. Only IPs meeting the
        minimum speed thresholds are included in results.
        """
        ip_region_map = self.read_ips(self.ip_file)
        if not ip_region_map:
            raise ValueError("No IPs found in CSV")

        successful_ips: List[IPPerformanceMetrics] = []
        for region, ips in ip_region_map.items():
            logging.info(f"Starting ping tests to filter IPs in region {region}.")
            filtered_ip = self.filter_ips_by_ping(ips)
            if not filtered_ip:
                logging.warning("No IPs passed the ping filter.")
                continue

            for ip, ping in filtered_ip:
                logging.info(f"Testing IP: {ip}")
                try:
                    download_speed = self.get_download_speed(ip)
                    if download_speed < self.min_download_speed:
                        logging.info(f"IP {ip} download speed too low: {download_speed}")
                        continue

                    upload_speed = self.get_upload_speed(ip)
                    if upload_speed < self.min_upload_speed:
                        logging.info(f"IP {ip} upload speed too low: {upload_speed}")
                        continue

                    successful_ips.append(IPPerformanceMetrics(
                        ip=ip,
                        ping=ping,
                        upload_speed=upload_speed,
                        download_speed=download_speed
                    ))
                except Exception as e:
                    logging.error(f"Unexpected error testing IP {ip}: {e}")

        return successful_ips

    def export_results(self, results: List[IPPerformanceMetrics]) -> None:
        """Write speed test results to a CSV file."""
        try:
            os.makedirs(os.path.dirname(self.output_file) or ".", exist_ok=True)
            with open(self.output_file, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(CSV_HEADERS)
                for result in results:
                    writer.writerow(result.to_csv_row())
            logging.info(f"Results exported to {self.output_file}")
        except Exception as e:
            raise IOError(f"Critical error: Failed to export results: {e}")


def main():
    """Entry point: run IP tests and export results."""
    try:
        tester = CloudflareIPTester()
        results = tester.run_tests()
        tester.export_results(results)
        if results:
            print("\nSuccessful IPs:")
            for result in results:
                print(f"  - {result}")
        else:
            print("No suitable IPs found.")
    except Exception as e:
        logging.critical(f"Critical error occurred: {e}")
        raise


if __name__ == "__main__":
    main()
