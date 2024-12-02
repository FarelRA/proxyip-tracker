import csv
import os
import configparser

def separate_ips_by_region(config_file):
    """
    Separate IPs into different text files based on their region.

    :param config_file: Path to the configuration file
    """
    # Read configuration
    config = configparser.ConfigParser()
    config.read(config_file)

    # Get output file naming parameters
    input_csv = config.get('separateIPs', 'input_csv', fallback='ip_performance.csv')
    file_prefix = config.get('separateIPs', 'file_prefix', fallback='')
    file_suffix = config.get('separateIPs', 'file_suffix', fallback='')
    save_dir = config.get('separateIPs', 'save_dir', fallback='result')
    file_extension = config.get('separateIPs', 'file_extension', fallback='.txt')

    # Check if files exist
    if not os.path.exists(input_csv):
        print(f"Error: Input CSV file '{input_csv}' not found.")
        return

    # Dictionary to store IPs by region
    regions = {}

    # Read the CSV file
    with open(input_csv, 'r', newline='') as csvfile:
        # Use DictReader to read CSV as dictionary
        csv_reader = csv.DictReader(csvfile)

        # Validate required columns
        required_columns = ['IP', 'Region', 'Download (Mbps)']
        for col in required_columns:
            if col not in csv_reader.fieldnames:
                raise ValueError(f"Required column '{col}' not found in CSV")

        # Group IPs by region
        for row in csv_reader:
            region = row['Region']
            ip = row['IP']
            download_speed = float(row['Download (Mbps)'])

            # Initialize list for region if not exists
            if region not in regions:
                regions[region] = []

            # Add IP to region's list
            regions[region].append((ip, download_speed))

    # Write IPs to region-specific files
    for region, ips in regions.items():
        # Sanitize region name to be filename-friendly
        safe_region = ''.join(c for c in region if c.isalnum() or c in (' ', '_')).rstrip()

        # Construct output filename
        output_filename = os.path.join(save_dir,
                                       f"{file_prefix}{safe_region}{file_suffix}{file_extension}")

        # Write IPs to file
        with open(output_filename, 'w') as outfile:
            # Sort IPs by download speed in descending order
            sorted_ips = sorted(ips, key=lambda x: x[1], reverse=True)

            # Write IPs to file
            for ip, speed in sorted_ips:
                outfile.write(f"{ip}\n")

        print(f"Created {output_filename} with {len(sorted_ips)} IPs")

def main():
    # Default paths
    config_file = 'config.ini'

    if not os.path.exists(config_file):
        print(f"Error: Config file '{config_file}' not found.")
        return

    # Separate IPs
    separate_ips_by_region(config_file)

if __name__ == '__main__':
    main()