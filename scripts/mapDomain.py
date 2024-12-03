import csv
import configparser
from operator import itemgetter

def filter_ips():
    # Load configuration
    config = configparser.ConfigParser()
    config.read('config.ini')

    input_csv = config.get('mapDomain', 'input_csv')
    output_csv = config.get('mapDomain', 'output_csv')

    # Load domain mapping and max IPs per domain
    domain_map = {}
    max_ips = {}
    for region, mapping in config.items('mapDomain.map'):
        domain, max_ip = mapping.split(',')
        domain_map[region.strip()] = domain.strip()
        max_ips[region.strip()] = int(max_ip.strip())

    # Read and filter input CSV
    filtered_data = []
    with open(input_csv, 'r') as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            region = row['Region']
            if region in domain_map:
                filtered_data.append({
                    'Domain': domain_map[region],
                    'IP': row['IP'],
                    'Download': float(row['Download (Mbps)']),
                    'Region': region
                })

    # Sort data by Download (Mbps) and then by Domain
    filtered_data.sort(key=itemgetter('Domain', 'Download'), reverse=True)

    # Limit the number of IPs per domain
    domain_ip_count = {domain: 0 for domain in domain_map.values()}
    final_data = []
    for row in filtered_data:
        domain = row['Domain']
        if domain_ip_count[domain] < max_ips[row['Region']]:
            final_data.append({'Domain': domain, 'IP': row['IP']})
            domain_ip_count[domain] += 1

    # Write to output CSV
    with open(output_csv, 'w', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=['Domain', 'IP'])
        writer.writeheader()
        writer.writerows(final_data)

if __name__ == '__main__':
    filter_ips()
