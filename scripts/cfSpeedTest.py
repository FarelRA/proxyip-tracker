#!/usr/bin/env python3
"""
Cloudflare IP Performance Tester

This script tests Cloudflare IP addresses for performance metrics
including ping, upload, and download speeds across different regions.
"""

import os
import csv
import ssl
import time
import random
import typing
import logging
import ipaddress
import configparser
from io import StringIO
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import requests

# Optional dependencies with graceful fallback
try:
    import ping3
    PING_AVAILABLE = True
except ImportError:
    PING_AVAILABLE = False
    logging.warning("ping3 module not found. Ping functionality will be limited.")

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

@dataclass
class IPPerformanceMetrics:
    """
    Data class to store IP performance metrics.
    """
    ip: str
    region: str
    ping: int
    upload_speed: float
    download_speed: float

    def to_csv_row(self) -> List[str]:
        """Convert metrics to CSV row format."""
        return [
            self.ip,
            self.region,
            str(self.ping),
            f"{self.upload_speed:.2f}",
            f"{self.download_speed:.2f}"
        ]

class CloudflareIPTester:
    """
    Main class for testing Cloudflare IP addresses.
    """
    def __init__(self, config_path: str = 'config.ini'):
        """
        Initialize the tester with configuration settings.

        :param config_path: Path to the configuration file
        """
        self.config = configparser.ConfigParser()
        self.config.read(config_path)

        # Configuration parsing with type conversion and validation
        self.max_ips = self._get_config_int('cfSpeedTest', 'max_ips', 10)
        self.max_ping = self._get_config_int('cfSpeedTest', 'max_ping', 100)
        self.test_size = self._get_config_int('cfSpeedTest', 'test_size', 1024)
        self.min_download_speed = self._get_config_float('cfSpeedTest', 'min_download_speed', 5.0)
        self.min_upload_speed = self._get_config_float('cfSpeedTest', 'min_upload_speed', 2.0)
        self.output_file = self._get_config_str('cfSpeedTest', 'output_file', 'ip_performance.csv')
        self.ip_file = self._get_config_str('cfSpeedTest', 'file_ips', 'ips.txt')

        # Check OpenSSL availability
        self.openssl_available = bool(ssl.OPENSSL_VERSION)

    def _get_config_int(self, section: str, key: str, default: int) -> int:
        """Safely get integer configuration value."""
        try:
            return self.config.getint(section, key)
        except (configparser.NoOptionError, ValueError):
            logging.warning(f"Using default value {default} for {key}")
            return default

    def _get_config_float(self, section: str, key: str, default: float) -> float:
        """Safely get float configuration value."""
        try:
            return self.config.getfloat(section, key)
        except (configparser.NoOptionError, ValueError):
            logging.warning(f"Using default value {default} for {key}")
            return default

    def _get_config_str(self, section: str, key: str, default: str) -> str:
        """Safely get string configuration value."""
        try:
            return self.config.get(section, key)
        except configparser.NoOptionError:
            logging.warning(f"Using default value {default} for {key}")
            return default

    @staticmethod
    def read_ips(file_path: str) -> List[str]:
        """
        Read and validate IP addresses from a file.

        :param file_path: Path to the file containing IP addresses
        :return: List of valid IP addresses
        """
        try:
            with open(file_path, 'r') as file:
                ips = [
                    ip.strip() for ip in file
                    if ip.strip() and CloudflareIPTester.validate_ip(ip.strip())
                ]

            if not ips:
                raise ValueError("No valid IP addresses found in the file")

            return ips
        except FileNotFoundError:
            raise FileNotFoundError(f"IP file not found: {file_path}")
        except Exception as e:
            raise FileNotFoundError(f"Error reading IP file: {e}")

    @staticmethod
    def validate_ip(ip: str) -> bool:
        """
        Validate an IP address.

        :param ip: IP address to validate
        :return: True if valid, False otherwise
        """
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            logging.warning(f"Invalid IP address: {ip}")
            return False

    def fetch_cloudflare_colo_data(self) -> List[Dict[str, str]]:
        """
        Fetch Cloudflare colo data from a remote CSV.

        :return: List of colo data dictionaries
        """
        try:
            csv_url = "https://raw.githubusercontent.com/Netrvin/cloudflare-colo-list/refs/heads/main/DC-Colos.csv"
            response = requests.get(csv_url, timeout=10)
            response.raise_for_status()

            return list(csv.DictReader(StringIO(response.text)))
        except requests.RequestException as e:
            logging.error(f"Error fetching Cloudflare colo data: {e}")
            return []

    def get_colo_from_ip(self, ip: str) -> Optional[str]:
        """
        Fetch the colo code for a given IP address.

        :param ip: IP address to check
        :return: Colo code or None
        """
        try:
            url = f"https://speed.cloudflare.com/cdn-cgi/trace"
            headers = {'Host': 'speed.cloudflare.com'}

            params = {
                'resolve': f"speed.cloudflare.com:443:{ip}",
                **({"alpn": "h2,http/1.1", "utls": "random"} if self.openssl_available else {})
            }

            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()

            for line in response.text.splitlines():
                if line.startswith("colo="):
                    logging.info(f"Colo: {line.split("=")[1]}")
                    return line.split("=")[1]
        except requests.RequestException as e:
            logging.error(f"Error fetching colo for IP {ip}: {e}")

        return None

    def get_region_from_colo(self, colo: str, colo_data: List[Dict[str, str]]) -> str:
        """
        Find region for a given colo code.

        :param colo: Colo code
        :param colo_data: List of colo data
        :return: Region name
        """
        for row in colo_data:
            if row.get('colo') == colo:
                logging.info(f"Region: {row.get('region', 'Unknown').replace(" ", "_")}")
                return row.get('region', 'Unknown').replace(" ", "_")
        return "Unknown"

    def get_ping(self, ip: str) -> int:
        """
        Get ping for an IP address.

        :param ip: IP address to ping
        :return: Ping time in milliseconds
        """
        try:
            start_time = time.time()
            response_time = ping3.ping(ip, timeout=self.max_ping/1000)

            if response_time is not None and response_time > 0:
                return int(response_time * 1000)

            logging.info(f"Ping time: {(time.time() - start_time) * 1000}")
            return int((time.time() - start_time) * 1000)
        except Exception as e:
            logging.error(f"Ping failed for {ip}: {e}")
            return -1

    def get_ping_fallback(self, ip: str) -> int:
        """
        Get ping for an IP address. Fallback method using requests.

        :param ip: IP address to ping
        :return: Ping time in milliseconds
        """
        download_size = 8
        url = f"https://speed.cloudflare.com/__down?bytes={download_size}"
        headers = {'Host': 'speed.cloudflare.com'}

        params = {
            'resolve': f"speed.cloudflare.com:443:{ip}",
            **({"alpn": "h2,http/1.1", "utls": "random"} if self.openssl_available else {})
        }

        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, params=params, timeout=2)
            end_time = time.time()

            rtt = int((end_time - start_time) * 1000)  # Convert to milliseconds
            logging.info(f"HTTP-based ping for IP {ip}: {rtt} ms")
            return rtt
        except requests.RequestException as e:
            logging.error(f"HTTP-based ping failed for IP {ip}: {e}")
            return -1

    def get_download_speed(self, ip: str) -> float:
        """
        Test download speed for an IP.

        :param ip: IP address to test
        :return: Download speed in Mbps
        """
        download_size = self.test_size * 1024
        url = f"https://speed.cloudflare.com/__down?bytes={download_size}"
        headers = {'Host': 'speed.cloudflare.com'}

        params = {
            'resolve': f"speed.cloudflare.com:443:{ip}",
            **({"alpn": "h2,http/1.1", "utls": "random"} if self.openssl_available else {})
        }

        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, params=params, timeout=10)
            download_time = time.time() - start_time

            logging.info(f"Download speed: {round(download_size / download_time * 8 / 1_000_000, 2)} Mbps")
            return round(download_size / download_time * 8 / 1_000_000, 2)
        except requests.RequestException:
            return 0.0

    def get_upload_speed(self, ip: str) -> float:
        """
        Test upload speed for an IP.

        :param ip: IP address to test
        :return: Upload speed in Mbps
        """
        upload_size = int(self.test_size * 1024)
        url = 'https://speed.cloudflare.com/__up'
        headers = {
            'Content-Type': 'multipart/form-data',
            'Host': 'speed.cloudflare.com'
        }

        params = {
            'resolve': f"speed.cloudflare.com:443:{ip}",
            **({"alpn": "h2,http/1.1", "utls": "random"} if self.openssl_available else {})
        }

        files = {'file': ('sample.bin', b"\x00" * upload_size)}

        try:
            start_time = time.time()
            requests.post(url, headers=headers, params=params, files=files, timeout=10)
            upload_time = time.time() - start_time

            logging.info(f"Upload speed: {round(upload_size / upload_time * 8 / 1_000_000, 2)} Mbps")
            return round(upload_size / upload_time * 8 / 1_000_000, 2)
        except requests.RequestException:
            return 0.0

    def map_ips_to_regions(self, ip_list):
        # Fetch colo data
        logging.info("Fetching Cloudflare colo data.")
        colo_data = self.fetch_cloudflare_colo_data()
        if not colo_data:
            raise RuntimeError("Critical error: Failed to fetch Cloudflare colo data.")

        # Dictionary to store regions and their IPs
        region_ip_map = {}

        # Process each IP
        for ip in ip_list:
            colo = self.get_colo_from_ip(ip)
            if not colo:
                logging.info(f"Could not determine colo for IP {ip}")
                continue

            region = self.get_region_from_colo(colo, colo_data)
            if not region:
                logging.info(f"Could not determine region for colo {colo}")
                continue

            # Add IP to the corresponding region
            region_ip_map.setdefault(region, []).append(ip)

        return region_ip_map

    def filter_ips_by_ping(self, ip_list: List[str]) -> List[Tuple[str, int]]:
        """
        Filter IPs based on ping response and return the top `max_ips` along with their ping times.

        :param ip_list: List of IP addresses to test
        :return: List of tuples (IP, ping) for the top `max_ips` based on lowest ping
        """
        ip_ping_results = []
        for ip in ip_list:
            try:
                if PING_AVAILABLE:
                    ping_time = self.get_ping(ip)
                else:
                    ping_time = self.get_ping_fallback(ip)

                if ping_time > 0 and ping_time <= self.max_ping:
                    ip_ping_results.append((ip, ping_time))
            except Exception as e:
                logging.warning(f"Ping test failed for {ip}: {e}")

        # Sort by ping time and select the top `max_ips`
        ip_ping_results.sort(key=lambda x: x[1])
        return ip_ping_results[:self.max_ips]

    def run_tests(self) -> List[IPPerformanceMetrics]:
        """
        Run comprehensive IP performance tests.

        :param stdscr: Curses window for display (optional)
        :return: List of successful IP performance metrics
        """
        # Read and shuffle IPs
        try:
            ip_list = self.read_ips(self.ip_file)
            random.shuffle(ip_list)
        except Exception as e:
            raise ValueError(f"Failed to read 'ip_list': {e}")

        # Get map of corresponding region for each ip
        logging.info("Getting region for each IPs.")
        ip_region_map = self.map_ips_to_regions(ip_list)
        if not ip_region_map:
            raise RuntimeError("Can not get regions of IPs")

        # Perform tests
        successful_ips: List[IPPerformanceMetrics] = []
        for region, ips in ip_region_map.items():
            # Filter IPs by ping
            logging.info(f"Starting ping tests to filter IPs in region {region}.")
            filtered_ip = self.filter_ips_by_ping(ips)
            if not filtered_ip:
                logging.warning("No IPs passed the ping filter.")
                continue

            # Testing IPs
            for ip, ping in filtered_ip:
                logging.info(f"Testing IP: {ip}")

                try:
                    # Speed tests
                    download_speed = self.get_download_speed(ip)
                    if download_speed < self.min_download_speed:
                        logging.info(f"IP {ip} download speed too low: {download_speed}")
                        continue

                    upload_speed = self.get_upload_speed(ip)
                    if upload_speed < self.min_upload_speed:
                        logging.info(f"IP {ip} upload speed too low: {upload_speed}")
                        continue

                    # Save successful metrics
                    successful_ips.append(IPPerformanceMetrics(
                        ip=ip,
                        region=region,
                        ping=ping,
                        upload_speed=upload_speed,
                        download_speed=download_speed
                    ))

                except Exception as e:
                    logging.error(f"Unexpected error testing IP {ip}: {e}")

        return successful_ips

    def export_results(self, results: List[IPPerformanceMetrics]) -> None:
        """
        Export test results to CSV.

        :param results: List of IP performance metrics
        """
        try:
            with open(self.output_file, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                # Write headers
                writer.writerow(['IP', 'Region', 'Ping (ms)', 'Upload (Mbps)', 'Download (Mbps)'])

                # Write results
                for result in results:
                    writer.writerow(result.to_csv_row())

            logging.info(f"Results exported to {self.output_file}")
        except Exception as e:
            raise IOError(f"Critical error: Failed to export results: {e}")

def main():
    """
    Main execution function with optional curses display.
    """
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
        raise  # Re-raise to terminate with a stack trace

if __name__ == "__main__":
    main()
