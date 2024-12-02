import requests
import zipfile
import io
import fnmatch
import configparser

def download_zip_file(url):
    """Download the ZIP file from the specified URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return io.BytesIO(response.content)
    except requests.exceptions.RequestException as e:
        raise SystemExit(f"Error during file download: {e}")

def extract_and_combine_files(zip_file, file_pattern):
    """Extract and combine content of files matching the pattern."""
    matching_files = fnmatch.filter(zip_file.namelist(), file_pattern)
    if not matching_files:
        raise FileNotFoundError(f"No files matching {file_pattern} found in the ZIP archive.")

    combined_content = []
    for file_name in matching_files:
        with zip_file.open(file_name) as file:
            lines = file.read().decode('utf-8').splitlines()
            combined_content.extend(line for line in lines if line.strip())

    return "\n".join(combined_content)

def save_to_file(content, output_file):
    """Save the combined content to a file."""
    with open(output_file, 'w') as file:
        file.write(content)
    print(f"Combined content saved to: {output_file}")

def process_zip_file(url, file_pattern, output_file):
    """Main function to download, process, and save the combined content."""
    print(f"Downloading ZIP file from: {url}")
    zip_data = download_zip_file(url)

    with zipfile.ZipFile(zip_data) as zip_file:
        print("Extracting and combining files...")
        combined_content = extract_and_combine_files(zip_file, file_pattern)

        print("Saving combined content to file...")
        save_to_file(combined_content, output_file)

def load_config(config_file):
    """Load configuration from a file."""
    config = configparser.ConfigParser()
    config.read(config_file)
    return config['getIPs']

# Usage example
if __name__ == "__main__":
    config_file = "config.ini"  # Path to your config file

    try:
        # Load configuration
        config = load_config(config_file)
        url = config.get('url')
        file_pattern = config.get('file_pattern')
        output_file = config.get('output_file')

        # Process the ZIP file
        process_zip_file(url, file_pattern, output_file)
    except Exception as e:
        print(e)