# Cloudflare proxyIP DNS Updater

This project automatically updates Cloudflare DNS records with the fastest proxy IP addresses found. It's designed to be run as a scheduled GitHub Actions workflow on a Ubuntu free runner.

## How it Works

1. **Discovering Proxy IPs (`scripts/getIPs.py`):** Fetches Oracle Cloud public CIDR ranges, connects to every IP on port 443 with TLS SNI set to `speed.cloudflare.com`, and checks if the response comes from Cloudflare's edge. Scans all IPv4 and IPv6 ranges with no limits using asyncio parallelism. Results are saved to `result/ips.txt`.

2. **IP Testing (`scripts/cfSpeedTest.py`):** From the `result/ips.txt`, maps IPs to regions via Cloudflare colo data, tests ping, download, and upload speed through real TLS socket connections to each proxy IP. Supports IPv4 and IPv6. Results saved to `result/tested-ips.csv`.

3. **Domain IP Mapping (`scripts/mapDomain.py`):** From the `result/tested-ips.csv`, maps the best-performing IPs to domains per region, sorted by download speed. Results saved to `result/domains-ips.csv`.

4. **Cloudflare Record Update (`scripts/cfRecUpdate.py`):** From `result/domains-ips.csv`, updates Cloudflare DNS records with the IP addresses. Automatically detects IP version — creates A records for IPv4 and AAAA records for IPv6. Intelligently updates existing records, creates new ones, and deletes extras.

5. **Workflow Automation:** A GitHub Actions workflow (`daily_update.yml`) schedules the entire process to run every three hours.

## GitHub Setup

1. **Repository:** Clone/Fork this repository to your GitHub account.

2. **Edit Configurations:** Edit the `config.ini` to your desired configs.

3. **Workflow Configuration:**
   - In your repository's settings (Settings > Secrets and variables > Actions > Secrets), add a secret named `CLOUDFLARE_API_TOKEN` with your Cloudflare API token.

4. **Workflow Dispatch (Optional):** You can manually trigger the workflow from the "Actions" tab of your repository if needed.

## Local Setup

1. **Repository:** Clone this repository with git.

2. **Edit Configurations:** Edit the `config.ini` to your desired configs.

3. **Set Environment Variables:**
   - Set environment variable named `CLOUDFLARE_API_TOKEN` with your Cloudflare API token.

4. **Running:**
   - To get the Proxy IPs, run `python "scripts/getIPs.py"`
   - Test the Proxy IPs, run `python "scripts/cfSpeedTest.py"`
   - Map the IPs to Domains, run `python "scripts/mapDomain.py"`
   - Finally, Update Cloudflare records, run `python "scripts/cfRecUpdate.py"`

## Configuration Guide

### 1. **Get IPs**
- **Purpose:** Discover Cloudflare proxy IPs within Oracle Cloud infrastructure by scanning all public CIDR ranges.
- **Settings:**
  - `url`: Oracle Cloud public IP ranges JSON URL (default: `https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json`).
  - `output_file`: Path to save the discovered proxy IPs (e.g., `result/ips.txt`).

### 2. **Cloudflare Speed Test (cfSpeedTest)**
- **Purpose:** Test the speed and quality of IPs for download/upload performance.
- **Settings:**
  - `file_ips`: Input file with collected IPs (e.g., `result/ips.txt`).
  - `max_ips`: Maximum number of IPs to test (e.g., 48).
  - `max_ping`: Maximum acceptable ping in ms (e.g., 320).
  - `test_size`: Data size in KB for testing download/upload speeds (e.g., 10240).
  - `min_download_speed`: Minimum acceptable download speed in Mbps (e.g., 20.0).
  - `min_upload_speed`: Minimum acceptable upload speed in Mbps (e.g., 20.0).
  - `output_file`: File to save the test results (e.g., `result/tested-ips.csv`).

### 3. **Map Domain**
- **Purpose:** Assign tested IPs to specific regions and domains.
- **Settings:**
  - `input_csv`: Input file with tested IPs (e.g., `result/tested-ips.csv`).
  - `output_csv`: Output file with mapped domains (e.g., `result/domains-ips.csv`).
- **Mapping Rules:**
  - Each line represent region with domain and max ips.
  - `{REGION}`: `{DOMAIN}`, `{MAX_IPS}`. e.g.:
    - `Europe: eu.proxy.farelra.my.id,5`
    - `Asia_Pacific: ap.proxy.farelra.my.id,10`


### 4. **Cloudflare Record Update (cfRecUpdate)**
- **Purpose:** Update Cloudflare DNS records based on the mapped domains and IPs. Automatically creates A records for IPv4 and AAAA records for IPv6.
- **Settings:**
  - `input_csv`: File with domains and their corresponding IPs (e.g., `result/domains-ips.csv`).
  - `zone_id`: Cloudflare Zone ID for updates.

Each section aligns with a specific step in the process, allowing for modular usage and configuration. Adjust paths and settings as needed to suit your environment.
## Disclaimer

This project is provided as-is.  Use it at your own risk.  Ensure you understand how it works and configure it correctly for your specific needs.  The author is not responsible for any issues or damages caused by using this project.

## Contributing

Contributions are welcome!  Feel free to open issues or submit pull requests.
