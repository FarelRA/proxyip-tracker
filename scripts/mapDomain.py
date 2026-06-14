import csv
import os
import configparser
from operator import itemgetter

def filter_ips():
    config = configparser.ConfigParser()
    config.read('config.ini')

    ip_csv = config.get('mapDomain', 'ip_csv')
    input_csv = config.get('mapDomain', 'input_csv')
    output_csv = config.get('mapDomain', 'output_csv')
    print(f"IP CSV path: {ip_csv}")
    print(f"Input CSV path: {input_csv}")
    print(f"Output CSV path: {output_csv}")

    # Load domain mapping and max IPs per domain (case-insensitive)
    print("Loading domain mapping and max IP limits...")
    domain_map = {}
    max_ips = {}
    for region, mapping in config.items('mapDomain.map'):
        domain, max_ip = mapping.split(',')
        region_lower = region.strip().lower()
        domain_map[region_lower] = domain.strip()
        max_ips[region_lower] = int(max_ip.strip())
        print(f"Mapped region '{region.strip()}' to domain '{domain.strip()}' with max IPs: {max_ip.strip()}")

    # Build IP -> Region lookup from ips.csv
    print(f"Building IP-to-region map from {ip_csv}...")
    ip_to_region = {}
    with open(ip_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ip_to_region[row['IP'].strip()] = row['Region'].strip()

    # Read tested-ips.csv and join with region from ips.csv
    print("Reading and filtering tested IPs...")
    filtered_data = []
    with open(input_csv, 'r') as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            ip = row['IP'].strip()
            region = ip_to_region.get(ip, '')
            if not region:
                print(f"Skipping IP {ip}: region not found")
                continue
            region_lower = region.lower()
            if region_lower in domain_map:
                print(f"Processing row: IP={ip}, Region={region}, Download={row['Download (Mbps)']}")
                filtered_data.append({
                    'Domain': domain_map[region_lower],
                    'IP': ip,
                    'Download': float(row['Download (Mbps)']),
                    'Region': region_lower
                })
            else:
                print(f"Skipping IP {ip} with region '{region}' (no mapping found)")

    # Sort data by Download (Mbps) and then by Domain
    print("Sorting data by Domain and Download speed...")
    filtered_data.sort(key=itemgetter('Domain', 'Download'), reverse=True)

    # Limit the number of IPs per domain
    print("Limiting the number of IPs per domain...")
    domain_ip_count = {domain: 0 for domain in domain_map.values()}
    final_data = []
    for row in filtered_data:
        domain = row['Domain']
        if domain_ip_count[domain] < max_ips[row['Region']]:
            print(f"Adding IP '{row['IP']}' to domain '{domain}'")
            final_data.append({'Domain': domain, 'IP': row['IP']})
            domain_ip_count[domain] += 1
        else:
            print(f"Skipping IP '{row['IP']}' for domain '{domain}' (max limit reached)")

    # Write to output CSV
    print("Writing data to output CSV...")
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    with open(output_csv, 'w', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=['Domain', 'IP'])
        writer.writeheader()
        writer.writerows(final_data)
    print(f"Output successfully written to {output_csv}")

if __name__ == '__main__':
    print("Starting IP filtering process...")
    filter_ips()
    print("Process completed.")
