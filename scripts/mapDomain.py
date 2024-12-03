import csv
import configparser
import os
from typing import Dict, List, Optional, Union

def read_config(config_path: str) -> Dict[str, Union[str, int]]:
    """
    Read and parse the configuration file for region to domain mapping, IP caps, and file paths.

    :param config_path: Path to the configuration file
    :return: Dictionary with configuration settings
    """
    config = configparser.ConfigParser()
    config.read(config_path)

    # Combine mappings from different sections and parse IP caps
    region_mapping = {}
    ip_caps = {}
    for region, value in config['mapDomain'].items():
        try:
            domain, cap = value.split(',')
            region_mapping[region.strip()] = domain.strip()
            ip_caps[domain.strip()] = int(cap.strip())
        except ValueError:
            print(f"Warning: Invalid entry for region '{region}'. Expected 'domain,cap'. Skipping.")

    # Read input and output file paths
    file_paths = {
        'input_csv': config['mapDomain.io'].get('input_csv', 'input_ips.csv'),
        'output_csv': config['mapDomain.io'].get('output_csv', 'filtered_ips.csv')
    }

    return {
        'region_mapping': region_mapping,
        'ip_caps': ip_caps,
        'file_paths': file_paths
    }

def map_region_to_domain(region: str, region_mapping: Dict[str, str]) -> str:
    """
    Map a region to its corresponding domain.

    :param region: Original region name
    :param region_mapping: Dictionary of region to domain mappings
    :return: Mapped domain
    """
    return region_mapping.get(region)

def process_input_csv(
    input_csv_path: str,
    region_mapping: Dict[str, str]
) -> List[Dict[str, Union[str, float]]]:
    """
    Process the input CSV file and prepare data for output.

    :param input_csv_path: Path to the input CSV file
    :param region_mapping: Dictionary mapping regions to domains
    :return: List of dictionaries with processed data
    """
    processed_data = []

    with open(input_csv_path, 'r', newline='') as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            # Map region to domain
            domain = map_region_to_domain(row['Region'], region_mapping)

            processed_row = {
                'Domain': domain,
                'IP': row['IP'],
                'Download_Speed': float(row['Download (Mbps)'])
            }

            processed_data.append(processed_row)

    return processed_data

def sort_and_cap_processed_data(
    processed_data: List[Dict[str, Union[str, float]]],
    ip_caps: Dict[str, int]
) -> List[Dict[str, Union[str, float]]]:
    """
    Sort processed data by Download speed (descending) and Domain,
    then cap the number of IPs per domain.

    :param processed_data: List of dictionaries with processed data
    :param ip_caps: Dictionary of maximum IP counts per domain
    :return: Sorted and capped list of dictionaries
    """
    # First, sort the data by Download speed (descending) and Domain
    sorted_data = sorted(processed_data, key=lambda x: (-x['Download_Speed'], x['Domain']))

    # Create a dictionary to track IP counts per domain
    domain_ip_counts = {}
    capped_data = []

    for row in sorted_data:
        domain = row['Domain']

        # Get the max allowed IPs for this domain (default to 0 if not specified)
        max_ips = ip_caps.get(domain, 0)

        # Initialize count for domain if not exists
        if domain not in domain_ip_counts:
            domain_ip_counts[domain] = 0

        # Add row if under IP cap
        if domain_ip_counts[domain] < max_ips:
            capped_data.append(row)
            domain_ip_counts[domain] += 1

    return capped_data

def write_output_csv(
    output_csv_path: str,
    sorted_data: List[Dict[str, Union[str, float]]]
) -> None:
    """
    Write sorted data to output CSV file.

    :param output_csv_path: Path to the output CSV file
    :param sorted_data: Sorted list of dictionaries to write
    """
    with open(output_csv_path, 'w', newline='') as csvfile:
        # Only write Domain and IP columns
        fieldnames = ['Domain', 'IP']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write header
        writer.writeheader()

        # Write sorted and capped rows
        for row in sorted_data:
            writer.writerow({
                'Domain': row['Domain'],
                'IP': row['IP']
            })

    print(f"Filtered, mapped, and capped IPs saved to {output_csv_path}")

def validate_input_csv(input_csv_path: str) -> bool:
    """
    Validate the input CSV file structure.

    :param input_csv_path: Path to the input CSV file
    :return: True if CSV is valid, False otherwise
    """
    required_columns = ['IP', 'Region', 'Ping (ms)', 'Upload (Mbps)', 'Download (Mbps)']

    try:
        with open(input_csv_path, 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile)

            # Check if all required columns are present
            csv_columns = reader.fieldnames or []
            missing_columns = set(required_columns) - set(csv_columns)

            if missing_columns:
                print(f"Missing columns: {missing_columns}")
                return False

            return True
    except FileNotFoundError:
        print(f"Input CSV file not found: {input_csv_path}")
        return False
    except Exception as e:
        print(f"Error validating input CSV: {e}")
        return False

def filter_and_map_ips(
    input_csv_path: str,
    output_csv_path: str,
    config_path: Optional[str] = None
) -> bool:
    """
    Main function to filter and map IPs from input CSV to output CSV.

    :param input_csv_path: Path to input CSV file
    :param output_csv_path: Path to output CSV file
    :param config_path: Optional path to configuration file
    :return: True if processing was successful, False otherwise
    """
    # Use default config path if not provided
    if config_path is None:
        config_path = 'config.ini'

    # Validate input CSV
    if not validate_input_csv(input_csv_path):
        return False

    try:
        # Read region to domain mapping and IP caps
        config = read_config(config_path)
        region_mapping = config['region_mapping']
        ip_caps = config['ip_caps']

        # Process input CSV
        processed_data = process_input_csv(input_csv_path, region_mapping)

        # Sort and cap processed data
        sorted_capped_data = sort_and_cap_processed_data(processed_data, ip_caps)

        # Write output CSV
        write_output_csv(output_csv_path, sorted_capped_data)

        return True

    except Exception as e:
        print(f"Error processing IPs: {e}")
        return False

def main():
    """
    Example usage of the IP filtering and mapping function.
    """
    # Read the configuration
    config_path = 'config.ini'
    config = read_config(config_path)

    input_csv_path = config['file_paths']['input_csv']
    output_csv_path = config['file_paths']['output_csv']

    # Run the IP filtering and mapping
    success = filter_and_map_ips(input_csv_path, output_csv_path, config_path)

    if success:
        print("IP filtering and mapping completed successfully.")
    else:
        print("IP filtering and mapping failed.")

if __name__ == '__main__':
    main()
