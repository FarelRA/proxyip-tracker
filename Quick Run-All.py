import os
import subprocess
import sys

from pathlib import Path

# Import the other Python scripts as modules
from testProxyIP import main as test_proxy_ip
from filterIPs import get_top_fastest_ips, print_top_ips
from cfRecUpdate import CloudflareDNSUpdater, logging

# Configure logging (consistent with cfRecUpdate.py)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run_all():
    """Runs all the steps equivalent to the bash script."""

    # 1. Run testProxyIP.py
    logger.info("Running testProxyIP.py...")
    test_proxy_ip()

    # 2. Run filterIPs.py and capture the output
    logger.info("Running filterIPs.py...")
    top_ips = get_top_fastest_ips("ip.csv")
    ip_addresses = [row['IP地址'] for row in top_ips]
    new_record = " ".join(ip_addresses)  # Space-separated IPs
    logger.debug(f"New record value: {new_record}")

    # 3. Run cfRecUpdate.py using the filtered IPs
    # Get variables
    # Get API token (prefer environment variable, then optional file)
    api_token = sys.argv[1] or os.getenv('CLOUDFLARE_API_TOKEN')
    if not api_token:
        token_file = Path(__file__).parent / ".cloudflare_api_token"  # Store token in a file in the same directory
        if token_file.exists():
            with open(token_file, "r") as f:
                api_token = f.read().strip()
        else:
            logger.critical("API Token is not provided via environment variable or .cloudflare_api_token file")
            raise ValueError("Please provide the CLOUDFLARE_API_TOKEN environment variable or create a .cloudflare_api_token file")

    zone_id = sys.argv[2] or os.getenv('CLOUDFLARE_ZONE_ID')
    record_name = sys.argv[3] or os.getenv('CLOUDFLARE_RECORD_NAME')

    if not zone_id or not record_name:
        logger.critical("CLOUDFLARE_ZONE_ID or CLOUDFLARE_RECORD_NAME environment variable not set.")
        raise ValueError("Please set the required environment variables.")

    record_type = "A"  # Remains hardcoded as it's unlikely to change

    dns_updater = CloudflareDNSUpdater(api_token, zone_id)
    try:
        updated_records = dns_updater.update_multiple_dns_records(
            record_name=record_name,
            record_type=record_type,
            new_content=new_record.split(),  # Split the space-separated string into a list
            proxied=False,  # Set proxied as needed
            ttl=1
        )
        logger.info("Successfully updated records")
        for record in updated_records:
            logger.debug(f"Updated Record: {record}")
    except Exception as e:
        logger.exception(f"An error occurred during Cloudflare update: {e}")



if __name__ == "__main__":
    run_all()
