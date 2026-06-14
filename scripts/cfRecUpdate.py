import os
import requests
import csv
import configparser
import ipaddress
from typing import List, Dict, Any, Optional
import logging

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Config ---
CONFIG_FILE = "config.ini"
KEY_FILE_DOMAINS = "file_domains"
KEY_ZONE_ID = "zone_id"
KEY_API_URL = "api_url"

# --- Config defaults ---
DEFAULT_FILE_DOMAINS = "result/domains-ips.csv"
DEFAULT_ZONE_ID = ""
DEFAULT_CF_API_BASE = "https://api.cloudflare.com/client/v4"

# --- Cloudflare API ---
# Environment variable that must contain the API token
ENV_API_TOKEN = "CLOUDFLARE_API_TOKEN"

# --- DNS ---
RECORD_TYPE_A = "A"
RECORD_TYPE_AAAA = "AAAA"
IPV6_VERSION = 6


class CloudflareDNSUpdater:
    """
    Manages Cloudflare DNS records for a specific zone.

    Provides methods to list, create, update, and delete DNS records
    via the Cloudflare API v4. Designed to sync a set of IPs to a
    domain's A and AAAA records.
    """

    def __init__(self, api_token: str, zone_id: str, base_url: str = DEFAULT_CF_API_BASE):
        """Initialize with API credentials and zone identifier."""
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        self.zone_id = zone_id
        logger.info("CloudflareDNSUpdater initialized")

    def get_dns_records(self, record_name: Optional[str] = None,
                        record_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch DNS records, optionally filtered by name and/or type."""
        logger.info("Retrieving DNS records")
        params = {}
        if record_name:
            params['name'] = record_name
        if record_type:
            params['type'] = record_type

        response = requests.get(
            f"{self.base_url}/zones/{self.zone_id}/dns_records",
            headers=self.headers,
            params=params
        )
        response_data = response.json()

        if not response_data['success']:
            logger.error(f"Failed to retrieve DNS records: {response_data['errors']}")
            raise Exception(f"Failed to retrieve DNS records: {response_data['errors']}")

        return response_data['result']

    def update_multiple_dns_records(
        self,
        record_name: str,
        record_type: str,
        new_content: List[str],
        proxied: bool = False,
        ttl: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Sync DNS records to match the given list of IPs.

        Strategy:
        1. Fetch existing records for the domain and type.
        2. Update in-place where possible (reuse existing record IDs).
        3. Create new records for surplus IPs.
        4. Delete any extra existing records.

        This minimizes API churn and avoids unnecessary create/delete cycles.
        """
        logger.info(f"Updating DNS records for {record_name} with type {record_type}")
        existing_records = self.get_dns_records(record_name, record_type)
        logger.debug(f"Existing records: {existing_records}")

        updated_records = []
        existing_set = {(rec['content'], rec['name'], rec['type']) for rec in existing_records}

        # Only process IPs that aren't already present
        new_content_filtered = [
            ip for ip in new_content
            if (ip, record_name, record_type) not in existing_set
        ]
        logger.debug(f"Filtered new content (non-duplicates): {new_content_filtered}")

        # Existing records that don't appear in the new content
        remaining_existing_records = [
            rec for rec in existing_records
            if (rec['content'], rec['name'], rec['type']) not in {(ip, record_name, record_type) for ip in new_content}
        ]

        # Update or create records
        for i, content in enumerate(new_content_filtered):
            if i < len(remaining_existing_records):
                record = remaining_existing_records[i]
                logger.info(f"Updating record {record['id']} with new content: {content}")
                updated_record = self.update_dns_record(
                    record_id=record['id'],
                    record_type=record_type,
                    name=record_name,
                    content=content,
                    proxied=proxied,
                    ttl=ttl
                )
                updated_records.append(updated_record)
            else:
                logger.info(f"Creating new record with content: {content}")
                new_record = self.create_dns_record(
                    record_type=record_type,
                    name=record_name,
                    content=content,
                    proxied=proxied,
                    ttl=ttl
                )
                updated_records.append(new_record)

        # Delete any remaining excess records
        for extra_record in remaining_existing_records[len(new_content_filtered):]:
            logger.info(f"Deleting extra record with content: {extra_record['content']}")
            self.delete_dns_record(extra_record['id'])

        logger.info(f"Completed updating DNS records for {record_name}")
        return updated_records

    def update_dns_record(self, record_id: str, record_type: str, name: str,
                          content: str, proxied: bool, ttl: int) -> Dict[str, Any]:
        """Update a single DNS record by its API ID."""
        logger.debug(f"Updating record ID {record_id} to content: {content}")
        payload = {
            "type": record_type,
            "name": name,
            "content": content,
            "proxied": proxied,
            "ttl": ttl
        }

        response = requests.put(
            f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}",
            headers=self.headers,
            json=payload
        )
        response_data = response.json()

        if not response_data['success']:
            logger.error(f"Failed to update DNS record: {response_data['errors']}")
            raise Exception(f"Failed to update DNS record: {response_data['errors']}")

        return response_data['result']

    def create_dns_record(self, record_type: str, name: str, content: str,
                          proxied: bool, ttl: int) -> Dict[str, Any]:
        """Create a new DNS record."""
        logger.debug(f"Creating record with content: {content}")
        payload = {
            "type": record_type,
            "name": name,
            "content": content,
            "proxied": proxied,
            "ttl": ttl
        }

        response = requests.post(
            f"{self.base_url}/zones/{self.zone_id}/dns_records",
            headers=self.headers,
            json=payload
        )
        response_data = response.json()

        if not response_data['success']:
            logger.error(f"Failed to create DNS record: {response_data['errors']}")
            raise Exception(f"Failed to create DNS record: {response_data['errors']}")

        return response_data['result']

    def delete_dns_record(self, record_id: str) -> bool:
        """Delete a DNS record by its API ID."""
        logger.info(f"Deleting record ID {record_id}")
        response = requests.delete(
            f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}",
            headers=self.headers
        )
        response_data = response.json()

        if not response_data['success']:
            logger.error(f"Failed to delete DNS record: {response_data['errors']}")
            raise Exception(f"Failed to delete DNS record: {response_data['errors']}")

        return True


def load_config():
    """Read config.ini and return the ConfigParser object."""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config


def read_input_csv(input_csv: str) -> Dict[str, List[str]]:
    """
    Read the domain-to-IP CSV and group IPs by domain.

    Expects a CSV with columns 'Domain' and 'IP' (produced by mapDomain.py).
    Returns a dict mapping each domain to its list of assigned IPs.
    """
    logger.info(f"Reading input CSV: {input_csv}")
    domain_ips = {}
    with open(input_csv, 'r') as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            domain = row['Domain']
            ip = row['IP']
            if domain not in domain_ips:
                domain_ips[domain] = []
            domain_ips[domain].append(ip)
    return domain_ips


def get_record_type(ip: str) -> str:
    """
    Determine the DNS record type (A or AAAA) based on the IP version.

    Uses ipaddress module to detect IPv4 vs IPv6. Returns 'A' for IPv4
    and 'AAAA' for IPv6.
    """
    try:
        addr = ipaddress.ip_address(ip)
        return RECORD_TYPE_AAAA if addr.version == IPV6_VERSION else RECORD_TYPE_A
    except ValueError:
        return RECORD_TYPE_A


def main():
    """Entry point: read IP mappings and sync them to Cloudflare DNS."""
    config = load_config()
    input_csv = config.get('cfRecUpdate', KEY_FILE_DOMAINS, fallback=DEFAULT_FILE_DOMAINS)
    zone_id = config.get('cfRecUpdate', KEY_ZONE_ID, fallback=DEFAULT_ZONE_ID)
    api_url = config.get('cfRecUpdate', KEY_API_URL, fallback=DEFAULT_CF_API_BASE)
    api_token = os.getenv(ENV_API_TOKEN)

    if not api_token:
        logger.critical("API Token is not provided via environment variable.")
        raise ValueError("Please provide the CLOUDFLARE_API_TOKEN environment variable.")

    dns_updater = CloudflareDNSUpdater(api_token, zone_id, base_url=api_url)

    # Process each domain's IPs, updating A and AAAA records separately
    domain_ips = read_input_csv(input_csv)
    for domain, ips in domain_ips.items():
        a_ips = [ip for ip in ips if get_record_type(ip) == RECORD_TYPE_A]
        aaaa_ips = [ip for ip in ips if get_record_type(ip) == RECORD_TYPE_AAAA]

        if a_ips:
            logger.info(f"Updating A records for domain: {domain}")
            dns_updater.update_multiple_dns_records(
                record_name=domain,
                record_type=RECORD_TYPE_A,
                new_content=a_ips,
                proxied=False,
                ttl=1
            )

        if aaaa_ips:
            logger.info(f"Updating AAAA records for domain: {domain}")
            dns_updater.update_multiple_dns_records(
                record_name=domain,
                record_type=RECORD_TYPE_AAAA,
                new_content=aaaa_ips,
                proxied=False,
                ttl=1
            )

    logger.info("DNS records updated successfully.")


if __name__ == "__main__":
    main()
