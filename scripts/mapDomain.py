import csv
import configparser
from operator import itemgetter

def filter_ips():
    # Load configuration
    print("Loading configuration...")
    config = configparser.ConfigParser()
    config.read('config.ini')

    input_csv = config.get('mapDomain', 'input_csv')
    output_csv = config.get('mapDomain', 'output_csv')
    print(f"Input CSV path: {input_csv}")
    print(f"Output CSV path: {output_csv}")

    # Load domain mapping and max IPs per domain (case-insensitive)
    print("Loading domain mapping and max IP limits (case-insensitive)...")
    domain_map = {}
    max_ips = {}
    for region, mapping in config.items('mapDomain.map'):
        domain, max_ip = mapping.split(',')
        region_lower = region.strip().lower()  # Make region case-insensitive
        domain_map[region_lower] = domain.strip()
        max_ips[region_lower] = int(max_ip.strip())
        print(f"Mapped region '{region.strip()}' to domain '{domain.strip()}' with max IPs: {max_ip.strip()}")

    # Read and filter input CSV
    print("Reading and filtering input CSV...")
    filtered_data = []
    with open(input_csv, 'r') as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            region = row['Region'].strip().lower()  # Normalize region to lower case
            if region in domain_map:
                print(f"Processing row: IP={row['IP']}, Region={row['Region']}, Download={row['Download (Mbps)']}")
                filtered_data.append({
                    'Domain': domain_map[region],
                    'IP': row['IP'],
                    'Download': float(row['Download (Mbps)']),
                    'Region': region
                })
            else:
                print(f"Skipping row with Region '{row['Region']}' (no mapping found)")

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
    with open(output_csv, 'w', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=['Domain', 'IP'])
        writer.writeheader()
        writer.writerows(final_data)
    print(f"Output successfully written to {output_csv}")

if __name__ == '__main__':
    print("Starting IP filtering process...")
    filter_ips()
    print("Process completed.")
