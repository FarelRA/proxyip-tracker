import csv
import os
import configparser
from operator import itemgetter

# --- Config keys ---
CONFIG_FILE = "config.ini"
KEY_FILE_IPS = "file_ips"
KEY_FILE_TESTS = "file_tests"
KEY_OUTPUT_FILE = "output_file"

# --- Config defaults ---
DEFAULT_FILE_IPS = "result/ips.csv"
DEFAULT_FILE_TESTS = "result/tested-ips.csv"
DEFAULT_OUTPUT_FILE = "result/domains-ips.csv"

# --- CSV column names ---
# These must match the headers in ips.csv and tested-ips.csv
COL_IP = "IP"
COL_REGION = "Region"
COL_DOWNLOAD = "Download (Mbps)"

# --- Dict keys ---
# Internal keys used for the filtered_data dict
KEY_DOMAIN = "Domain"
KEY_IP = "IP"
KEY_DOWNLOAD = "Download"
KEY_REGION = "Region"

# --- Output ---
OUTPUT_HEADERS = [KEY_DOMAIN, KEY_IP]
SORT_REVERSE = True
INIT_COUNT = 0
FALLBACK_DIR = "."


def filter_ips():
    """
    Main pipeline step: join tested IPs with their regions, filter by
    configured domain map, cap per region, and write the result.

    Reads ips.csv for IP-to-region mapping, tested-ips.csv for performance
    data, and config.ini [mapDomain.map] to determine which regions map to
    which domains and how many IPs each region can contribute.
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    ip_csv = config.get('mapDomain', KEY_FILE_IPS, fallback=DEFAULT_FILE_IPS)
    input_csv = config.get('mapDomain', KEY_FILE_TESTS, fallback=DEFAULT_FILE_TESTS)
    output_file = config.get('mapDomain', KEY_OUTPUT_FILE, fallback=DEFAULT_OUTPUT_FILE)
    print(f"IP CSV path: {ip_csv}")
    print(f"Input CSV path: {input_csv}")
    print(f"Output file path: {output_file}")

    # Load domain mapping and max IPs per domain (case-insensitive)
    print("Loading domain mapping and max IP limits...")
    domain_map = {}
    max_ips = {}
    if config.has_section('mapDomain.map'):
        for region, mapping in config.items('mapDomain.map'):
            domain, max_ip = mapping.split(',')
            region_lower = region.strip().lower()
            domain_map[region_lower] = domain.strip()
            max_ips[region_lower] = int(max_ip.strip())
            print(f"Mapped region '{region.strip()}' to domain '{domain.strip()}' with max IPs: {max_ip.strip()}")
    else:
        print("Warning: [mapDomain.map] section not found in config. No domain mapping will be applied.")

    # Build IP -> Region lookup from ips.csv
    print(f"Building IP-to-region map from {ip_csv}...")
    ip_to_region = {}
    with open(ip_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ip_to_region[row[COL_IP].strip()] = row[COL_REGION].strip()

    # Read tested-ips.csv and join with region from ips.csv
    print("Reading and filtering tested IPs...")
    filtered_data = []
    with open(input_csv, 'r') as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            ip = row[COL_IP].strip()
            region = ip_to_region.get(ip, '')
            if not region:
                print(f"Skipping IP {ip}: region not found")
                continue
            region_lower = region.lower()
            if region_lower in domain_map:
                print(f"Processing row: IP={ip}, Region={region}, Download={row[COL_DOWNLOAD]}")
                filtered_data.append({
                    KEY_DOMAIN: domain_map[region_lower],
                    KEY_IP: ip,
                    KEY_DOWNLOAD: float(row[COL_DOWNLOAD]),
                    KEY_REGION: region_lower
                })
            else:
                print(f"Skipping IP {ip} with region '{region}' (no mapping found)")

    # Sort by domain then download speed (highest first) so the best IPs
    # are selected first when we apply the per-domain cap
    print("Sorting data by Domain and Download speed...")
    filtered_data.sort(key=itemgetter(KEY_DOMAIN, KEY_DOWNLOAD), reverse=SORT_REVERSE)

    # Cap the number of IPs per (domain, region) pair so each region
    # independently gets its quota even when all map to the same domain
    print("Limiting the number of IPs per domain per region...")
    region_count = {}
    final_data = []
    for row in filtered_data:
        domain = row[KEY_DOMAIN]
        region = row[KEY_REGION]
        key = (domain, region)
        if region_count.get(key, INIT_COUNT) < max_ips[region]:
            print(f"Adding IP '{row[KEY_IP]}' to domain '{domain}' (region {region})")
            final_data.append({KEY_DOMAIN: domain, KEY_IP: row[KEY_IP]})
            region_count[key] = region_count.get(key, INIT_COUNT) + 1
        else:
            print(f"Skipping IP '{row[KEY_IP]}' for domain '{domain}' region '{region}' (max limit reached)")

    # Write the final domain-to-IP mapping to CSV
    print("Writing data to output CSV...")
    os.makedirs(os.path.dirname(output_file) or FALLBACK_DIR, exist_ok=True)
    with open(output_file, 'w', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()
        writer.writerows(final_data)
    print(f"Output successfully written to {output_file}")


if __name__ == '__main__':
    print("Starting IP filtering process...")
    filter_ips()
    print("Process completed.")
