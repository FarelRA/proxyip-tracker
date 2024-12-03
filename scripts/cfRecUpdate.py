import os
import csv
import requests
import configparser
import logging
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class CloudflareDNSUpdater:
    def __init__(self, api_token, zone_id):
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        self.zone_id = zone_id
        logger.info("CloudflareDNSUpdater initialized")

    def get_dns_records(self, record_name: str, record_type: str) -> List[Dict[str, Any]]:
        logger.info(f"Retrieving DNS records for name={record_name}, type={record_type}")
        params = {"name": record_name, "type": record_type}
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

    def update_dns_record(self, record_id: str, record_type: str, name: str, content: str, proxied: bool = False, ttl: int = 1) -> Dict[str, Any]:
        logger.info(f"Updating DNS record ID={record_id} with content={content}")
        payload = {"type": record_type, "name": name, "content": content, "proxied": proxied, "ttl": ttl}
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

    def create_dns_record(self, record_type: str, name: str, content: str, proxied: bool = False, ttl: int = 1) -> Dict[str, Any]:
        logger.info(f"Creating new DNS record for {name} with content={content}")
        payload = {"type": record_type, "name": name, "content": content, "proxied": proxied, "ttl": ttl}
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

def main():
    # Load configuration
    config = configparser.ConfigParser()
    config.read("config.ini")

    input_csv = config.get("cfRecUpdate", "input_csv")
    zone_id = config.get("cfRecUpdate", "zone_id")
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    if not api_token:
        logger.critical("CLOUDFLARE_API_TOKEN environment variable is not set")
        raise ValueError("API token not provided. Please set the CLOUDFLARE_API_TOKEN environment variable")

    # Initialize updater
    dns_updater = CloudflareDNSUpdater(api_token, zone_id)
    existing_records = dns_updater.get_dns_records(domain, record_type)

    # Process input CSV
    logger.info(f"Reading input CSV: {input_csv}")
    try:
        with open(input_csv, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                domain = row["Domain"]
                ip = row["IP"]
                record_type = "A"  # Assuming "A" records for IP addresses
                logger.info(f"Processing DNS record for domain={domain} with IP={ip}")
                try:
                    if existing_records:
                        logger.info(f"Existing DNS record found. Updating record.")
                        dns_updater.update_dns_record(
                            record_id=existing_records[0]["id"],
                            record_type=record_type,
                            name=domain,
                            content=ip,
                            proxied=False,
                            ttl=1
                        )
                    else:
                        logger.info(f"No existing record found. Creating new record.")
                        dns_updater.create_dns_record(
                            record_type=record_type,
                            name=domain,
                            content=ip,
                            proxied=False,
                            ttl=1
                        )
                except Exception as e:
                    logger.error(f"Failed to process DNS record for {domain}: {e}")
    except FileNotFoundError:
        logger.critical(f"Input CSV file not found: {input_csv}")
        raise

    logger.info("DNS records processing completed.")

if __name__ == "__main__":
    main()
