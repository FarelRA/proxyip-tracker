# Cloudflare proxyIP DNS Updater

This project automatically updates Cloudflare DNS records with the fastest proxy IP addresses found. It's designed to be run as a scheduled GitHub Actions workflow on a Ubuntu free runner.

## How it Works

1. **Discovering Proxy IPs (`scripts/getIPs.py`):** Fetches Oracle Cloud public CIDR ranges, connects to every IP on port 443 with TLS SNI set to `speed.cloudflare.com`, and checks if the response comes from Cloudflare's edge. Scans all IPv4 and IPv6 ranges with no limits using asyncio parallelism. Results saved to `result/ips.csv`.

2. **IP Testing (`scripts/cfSpeedTest.py`):** Reads `result/ips.csv`, groups IPs by region, tests ping, download, and upload speed through real TLS socket connections to each proxy IP. Supports IPv4 and IPv6. Results saved to `result/tested-ips.csv`.

3. **Domain IP Mapping (`scripts/mapDomain.py`):** Joins `result/ips.csv` (region lookup) and `result/tested-ips.csv` (speed data) on IP, maps the best-performing IPs to domains per region, sorted by download speed. Results saved to `result/domains-ips.csv`.

4. **Cloudflare Record Update (`scripts/cfRecUpdate.py`):** Reads `result/domains-ips.csv`, updates Cloudflare DNS records with the IP addresses. Automatically detects IP version — creates A records for IPv4 and AAAA records for IPv6. Updates existing records in-place, creates new ones, and deletes extras.

5. **Workflow Automation:** A GitHub Actions workflow (`daily_update.yml`) schedules the entire process to run every twelve hours.

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
  - `ranges_url`: Oracle Cloud public IP ranges JSON URL (default: `https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json`).
  - `region_url`: Cloudflare colo-to-region mapping CSV URL (default: Netrvin/cloudflare-colo-list).
  - `timeout`: Per-connection timeout for proxy scanning in seconds (default: `1`).
  - `max_concurrent`: Maximum concurrent asyncio tasks (default: `2000`).
  - `fetch_cidrs_timeout`: HTTP timeout for fetching Oracle CIDRs in seconds (default: `30`).
  - `fetch_colo_timeout`: HTTP timeout for fetching colo CSV in seconds (default: `4`).
  - `output_file`: Path to save the discovered proxy IPs (default: `result/ips.csv`).

### 2. **Cloudflare Speed Test (cfSpeedTest)**
- **Purpose:** Test the speed and quality of IPs for ping, download, and upload performance.
- **Settings:**
  - `file_ips`: Input CSV with discovered IPs and regions (default: `result/ips.csv`).
  - `max_ips`: Maximum number of IPs to test per region (default: `24`).
  - `max_ping`: Maximum acceptable ping in ms (default: `896`).
  - `min_download_speed`: Minimum acceptable download speed in Mbps (default: `20.0`).
  - `min_upload_speed`: Minimum acceptable upload speed in Mbps (default: `20.0`).
  - `test_size`: Data size in KB for testing download/upload speeds (default: `10240`).
  - `timeout`: Per-connection timeout for all speed test operations in seconds (default: `4`).
  - `ping_workers`: Thread pool size for parallel ping tests (default: `20`).
  - `output_file`: File to save the test results (default: `result/tested-ips.csv`).

### 3. **Map Domain**
- **Purpose:** Assign tested IPs to specific regions and domains.
- **Settings:**
  - `file_ips`: CSV with IP-to-region mapping (default: `result/ips.csv`).
  - `file_tests`: CSV with tested IP performance data (default: `result/tested-ips.csv`).
  - `output_file`: Output CSV with domain-to-IP mapping (default: `result/domains-ips.csv`).
- **Mapping Rules (`[mapDomain.map]`):**
  - Each line maps a region to a domain and max IPs.
  - Format: `{REGION} = {DOMAIN},{MAX_IPS}` e.g.:
    - `Europe = proxy.farel.is-a.dev,5`
    - `Asia_Pacific = proxy.farel.is-a.dev,10`

### 4. **Cloudflare Record Update (cfRecUpdate)**
- **Purpose:** Update Cloudflare DNS records based on the mapped domains and IPs. Automatically creates A records for IPv4 and AAAA records for IPv6.
- **Settings:**
  - `api_url`: Cloudflare API base URL (default: `https://api.cloudflare.com/client/v4`).
  - `zone_id`: Cloudflare Zone ID for updates.
  - `file_domains`: CSV with domains and their corresponding IPs (default: `result/domains-ips.csv`).

Each section aligns with a specific step in the process, allowing for modular usage and configuration. Every config key has a sensible default — only `zone_id` and the `CLOUDFLARE_API_TOKEN` environment variable are required.

## License

This project is licensed under the GNU General Public License v3.0 — see the [LICENSE](LICENSE) file for details.

## Disclaimer

This project is provided as-is. Use it at your own risk. Ensure you understand how it works and configure it correctly for your specific needs. The author is not responsible for any issues or damages caused by using this project.

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.
