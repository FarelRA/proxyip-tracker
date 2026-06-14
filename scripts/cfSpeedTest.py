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
import threading
import logging
import configparser
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

CLOUDFLARE_HOST = "speed.cloudflare.com"
CLOUDFLARE_PORT = 443
TIMEOUT = 4

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = True

_local = threading.local()

def _run(coro):
    """Run a coroutine in a per-thread event loop (avoids creating a new loop per call)."""
    try:
        loop = _local.loop
    except AttributeError:
        loop = asyncio.new_event_loop()
        _local.loop = loop
    return loop.run_until_complete(coro)


@dataclass
class IPPerformanceMetrics:
    """Data class to store IP performance metrics."""
    ip: str
    ping: int
    upload_speed: float
    download_speed: float

    def to_csv_row(self) -> List[str]:
        """Convert metrics to CSV row format."""
        return [
            self.ip,
            str(self.ping),
            f"{self.upload_speed:.2f}",
            f"{self.download_speed:.2f}"
        ]


class CloudflareIPTester:
    """
    Main class for testing Cloudflare IP addresses.
    Uses real socket-level connections through target IPs.
    """
    def __init__(self, config_path: str = 'config.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)

        self.max_ips = self._get_config_int('cfSpeedTest', 'max_ips', 10)
        self.max_ping = self._get_config_int('cfSpeedTest', 'max_ping', 100)
        self.test_size = self._get_config_int('cfSpeedTest', 'test_size', 1024)
        self.min_download_speed = self._get_config_float('cfSpeedTest', 'min_download_speed', 5.0)
        self.min_upload_speed = self._get_config_float('cfSpeedTest', 'min_upload_speed', 2.0)
        self.output_file = self._get_config_str('cfSpeedTest', 'output_file', 'ip_performance.csv')
        self.ip_file = self._get_config_str('cfSpeedTest', 'file_ips', 'ips.csv')

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

    def _get_config_bool(self, section: str, key: str, default: bool) -> bool:
        try:
            return self.config.getboolean(section, key)
        except (configparser.NoOptionError, ValueError):
            logging.warning(f"Using default value {default} for {key}")
            return default

    @staticmethod
    def read_ips(file_path: str) -> Dict[str, List[str]]:
        """Read ips.csv and return dict of {region: [ip, ...]}."""
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

    async def _socket_request(self, ip: str, path: str, method: str = "GET",
                               body: Optional[bytes] = None) -> Tuple[int, bytes]:
        """
        Make an HTTP request through a specific proxy IP using raw TLS socket.
        Returns (status_code, response_body).
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, CLOUDFLARE_PORT, ssl=ssl_context,
                                        server_hostname=CLOUDFLARE_HOST),
                timeout=TIMEOUT
            )

            if method == "GET":
                req = (
                    f"GET {path} HTTP/1.1\r\n"
                    f"Host: {CLOUDFLARE_HOST}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()
            elif method == "POST":
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

            raw = b""
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=TIMEOUT)
                if not chunk:
                    break
                raw += chunk

            writer.close()
            await writer.wait_closed()

            # Parse HTTP response
            header_end = raw.find(b"\r\n\r\n")
            if header_end == -1:
                return 0, raw

            status_line = raw[:raw.find(b"\r\n")].decode(errors='replace')
            status_code = 0
            if status_line.startswith("HTTP/"):
                try:
                    status_code = int(status_line.split(" ")[1])
                except (IndexError, ValueError):
                    pass

            body = raw[header_end + 4:]
            return status_code, body

        except (asyncio.TimeoutError, ConnectionRefusedError, ConnectionResetError,
                ssl.SSLError, OSError, ValueError):
            return 0, b""

    def get_ping(self, ip: str) -> int:
        """Get ping via real proxy connection by measuring RTT."""
        start = time.time()
        status, _ = _run(self._socket_request(ip, "/cdn-cgi/trace"))
        if status == 200:
            rtt = int((time.time() - start) * 1000)
            logging.info(f"Ping for {ip}: {rtt} ms")
            return rtt
        return -1

    def get_download_speed(self, ip: str) -> float:
        """Test download speed through the proxy IP."""
        download_size = self.test_size * 1024
        path = f"/__down?bytes={download_size}"

        start = time.time()
        status, body = _run(self._socket_request(ip, path))
        if status != 200 or not body:
            return 0.0

        elapsed = time.time() - start
        if elapsed <= 0:
            return 0.0

        speed = round(len(body) * 8 / elapsed / 1_000_000, 2)
        logging.info(f"Download speed for {ip}: {speed} Mbps")
        return speed

    def get_upload_speed(self, ip: str) -> float:
        """Test upload speed through the proxy IP."""
        upload_size = int(self.test_size * 1024)
        body = b"\x00" * upload_size
        boundary = "----WebKitFormBoundary" + os.urandom(16).hex()
        payload = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="sample.bin"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + body + f"\r\n--{boundary}--\r\n".encode()

        path = "/__up"
        start = time.time()
        status, response_body = _run(
            self._socket_request_raw(ip, path, payload, boundary)
        )
        if status == 0:
            return 0.0

        elapsed = time.time() - start
        if elapsed <= 0:
            return 0.0

        speed = round(upload_size * 8 / elapsed / 1_000_000, 2)
        logging.info(f"Upload speed for {ip}: {speed} Mbps")
        return speed

    async def _socket_request_raw(self, ip: str, path: str, body: bytes,
                                    boundary: str) -> Tuple[int, bytes]:
        """Like _socket_request but for raw POST with multipart body."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, CLOUDFLARE_PORT, ssl=ssl_context,
                                        server_hostname=CLOUDFLARE_HOST),
                timeout=TIMEOUT
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
                chunk = await asyncio.wait_for(reader.read(4096), timeout=TIMEOUT)
                if not chunk:
                    break
                raw += chunk

            writer.close()
            await writer.wait_closed()

            header_end = raw.find(b"\r\n\r\n")
            if header_end == -1:
                return 0, raw

            status_line = raw[:raw.find(b"\r\n")].decode(errors='replace')
            status_code = 0
            if status_line.startswith("HTTP/"):
                try:
                    status_code = int(status_line.split(" ")[1])
                except (IndexError, ValueError):
                    pass

            return status_code, raw[header_end + 4:]

        except (asyncio.TimeoutError, ConnectionRefusedError, ConnectionResetError,
                ssl.SSLError, OSError, ValueError):
            return 0, b""

    def filter_ips_by_ping(self, ip_list: List[str]) -> List[Tuple[str, int]]:
        """Filter IPs based on ping response using multithreading."""
        def ping_ip(ip):
            return ip, self.get_ping(ip)

        ip_ping_results = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_ip = {executor.submit(ping_ip, ip): ip for ip in ip_list}
            for future in as_completed(future_to_ip):
                try:
                    ip, ping_time = future.result()
                    if ping_time > 0 and ping_time <= self.max_ping:
                        ip_ping_results.append((ip, ping_time))
                except Exception as e:
                    logging.error(f"Error pinging IP {future_to_ip[future]}: {e}")

        ip_ping_results.sort(key=lambda x: x[1])
        return ip_ping_results[:self.max_ips]

    def run_tests(self) -> List[IPPerformanceMetrics]:
        """Run comprehensive IP performance tests."""
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
        """Export test results to CSV."""
        try:
            os.makedirs(os.path.dirname(self.output_file) or ".", exist_ok=True)
            with open(self.output_file, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['IP', 'Ping (ms)', 'Upload (Mbps)', 'Download (Mbps)'])
                for result in results:
                    writer.writerow(result.to_csv_row())
            logging.info(f"Results exported to {self.output_file}")
        except Exception as e:
            raise IOError(f"Critical error: Failed to export results: {e}")


def main():
    """Main execution function."""
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
