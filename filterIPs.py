import csv
import sys

def get_top_fastest_ips(file_path, top_n=5):
    # Open the CSV file
    with open(file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)

        # Convert network latency to integer (extract the numeric value and ignore 'ms')
        rows = []
        for row in reader:
            try:
                latency = int(row['网络延迟'].replace(' ms', '').strip())
                row['网络延迟'] = latency
                rows.append(row)
            except ValueError:
                # Skip rows where latency can't be parsed
                continue

        # Sort rows by network latency in ascending order
        rows_sorted = sorted(rows, key=lambda x: x['网络延迟'])

        # Get top N (or fewer if not enough rows)
        top_rows = rows_sorted[:min(top_n, len(rows_sorted))]

        return top_rows

def print_top_ips(top_ips):
    # Generate a space-separated string of the IP addresses
    ip_addresses = [row['IP地址'] for row in top_ips]
    print(" ".join(ip_addresses))

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python filterIPs.py <path_to_csv_file>")
        sys.exit(1)

    file_path = sys.argv[1]
    top_ips = get_top_fastest_ips(file_path)
    print_top_ips(top_ips)
