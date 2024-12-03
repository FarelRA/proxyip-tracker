import os
import requests
import csv
import configparser
from typing import List, Dict, Any, Optional
import logging

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

    def get_dns_records(self, record_name: Optional[str] = None, record_type: Optional[str] = None) -> List[Dict[str, Any]]:
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
        logger.info(f"Updating DNS records for {record_name} with type {record_type}")
        existing_records = self.get_dns_records(record_name, record_type)
        logger.debug(f"Existing records: {existing_records}")

        updated_records = []
        existing_set = {(rec['content'], rec['name'], rec['type']) for rec in existing_records}

        # Remove matching records from both new_content and the processing loop
        new_content_filtered = [
            ip for ip in new_content
            if (ip, record_name, record_type) not in existing_set
        ]
        logger.debug(f"Filtered new content (non-duplicates): {new_content_filtered}")

        # Skip processing records already present in existing records
        remaining_existing_records = [
            rec for rec in existing_records
            if (rec['content'], rec['name'], rec['type']) not in {(ip, record_name, record_type) for ip in new_content}
        ]

        # Update or create filtered records
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

        # Delete extra records not in the new content
        for extra_record in remaining_existing_records[len(new_content_filtered):]:
            logger.info(f"Deleting extra record with content: {extra_record['content']}")
            self.delete_dns_record(extra_record['id'])

        logger.info(f"Completed updating DNS records for {record_name}")
        return updated_records

    def update_dns_record(self, record_id: str, record_type: str, name: str, content: str, proxied: bool = False, ttl: int = 1) -> Dict[str, Any]:
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

    def create_dns_record(self, record_type: str, name: str, content: str, proxied: bool = False, ttl: int = 1) -> Dict[str, Any]:
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
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config


def read_input_csv(input_csv: str) -> Dict[str, List[str]]:
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


def main():
    # Load configuration
    config = load_config()
    input_csv = config.get('cfRecUpdate', 'input_csv')
    zone_id = config.get('cfRecUpdate', 'zone_id')
    api_token = os.getenv('CLOUDFLARE_API_TOKEN')

    if not api_token:
        logger.critical("API Token is not provided via environment variable.")
        raise ValueError("Please provide the CLOUDFLARE_API_TOKEN environment variable.")

    dns_updater = CloudflareDNSUpdater(api_token, zone_id)

    # Read input CSV and process DNS records
    domain_ips = read_input_csv(input_csv)
    for domain, ips in domain_ips.items():
        logger.info(f"Updating records for domain: {domain}")
        dns_updater.update_multiple_dns_records(
            record_name=domain,
            record_type="A",  # Assuming "A" records, can be changed to another type if needed
            new_content=ips,
            proxied=False,
            ttl=1
        )

    logger.info("DNS records updated successfully.")


if __name__ == "__main__":
    main()