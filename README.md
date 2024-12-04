# Cloudflare proxyIP DNS Updater

This project automatically updates Cloudflare DNS records with the fastest IP addresses found by `iptest.exe`.  It's designed to be run as a scheduled GitHub Actions workflow on a Windows runner.

## How it Works

1. **Getting IPs (`scripts/getIPs.py`):** Downloads a ZIP file containing IP lists, extracts it, combines the IPs. Then saving the results to `result/ip.txt`.

2. **IP Testing (`scripts/cfSpeedTest.py`):** From the `result/ip.txt`, check the regions, ping, download, and upload speed. Then save the result to `result/tested-ips.csv`.

3. **Domain IP Mapping (`scripts/mapDomain.py`):** From the `result/tested-ips.csv`. Map the IPs to the corresponding domains, then sort it by download speed. Then save the result to `result/domains-ips.csv`.

4. **Cloudflare Record Update (`scripts/cfRecUpdate.py`):** From `result/domains-ips.csv`. Updates specified Cloudflare DNS records with the IP addresses.  It intelligently updates existing records, creates new ones if needed, and deletes any extra records.

5. **Workflow Automation:** A GitHub Actions workflow (`daily_update.yml`) schedules the entire process to run daily, every three hours.

## GitHub Setup

1. **Repository:** Clone this repository to your GitHub account.

2. **Edit Configurations:** Edit the `config.ini` to your desired configs.

3. **Workflow Configuration:**
   - In your repository's settings (Settings > Secrets and variables > Actions > Secrets), add a secret named `CLOUDFLARE_API_TOKEN` with your Cloudflare API token.

4. **Workflow Dispatch (Optional):** You can manually trigger the workflow from the "Actions" tab of your repository if needed.

## Local Setup

1. **Repository:** Clone this repository with git.

2. **Edit Configurations:** Edit the `config.ini` to your desired configs.

3. **Set Environment Variables:**
   - Set secret variable named `CLOUDFLARE_API_TOKEN` with your Cloudflare API token.

4. **Running:**
   - To get the Proxy IPs, run `python "scripts/getIPs.py"`
   - Test the Proxy IPs, run `python "scripts/cfSpeedTest.py"`
   - Map the IPs to Domains, run `python "scripts/mapDomain.py"`
   - Finally, Update Cloudflare records, run `python "scripts/cfRecUpdate.py"`

## Configuration Guide

### 1. **Get IPs**
- **Purpose:** Fetch IP addresses matching a specific pattern from a URL.
- **Settings:**
  - `url`: The source URL for IP files (e.g., `https://zip.baipiao.eu.org`).
  - `file_pattern`: Pattern to match files (e.g., `*-1-443.txt`).
  - `output_file`: Path to save the collected IPs (e.g., `result/ips.txt`).

### 2. **Cloudflare Speed Test (cfSpeedTest)**
- **Purpose:** Test the speed and quality of IPs for download/upload performance.
- **Settings:**
  - `file_ips`: Input file with collected IPs (e.g., `result/ips.txt`).
  - `max_ips`: Maximum number of IPs to test (e.g., 48).
  - `max_ping`: Maximum acceptable ping (e.g., 320 ms).
  - `test_size`: Data size for testing download/upload speeds (e.g., 5120 KB).
  - `min_download_speed`: Minimum acceptable download speed (e.g., 20 Mbps).
  - `min_upload_speed`: Minimum acceptable upload speed (e.g., 20 Mbps).
  - `force_ping_fallback`: Force to use ping fallback method (http method) regardless `ping3` availability (e.g., True).
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
- **Purpose:** Update Cloudflare DNS records based on the mapped domains and IPs.
- **Settings:**
  - `input_csv`: File with domains and their corresponding IPs (e.g., `result/domains-ips.csv`).
  - `zone_id`: Cloudflare Zone ID for updates.

Each section aligns with a specific step in the process, allowing for modular usage and configuration. Adjust paths and settings as needed to suit your environment.
## Disclaimer

This project is provided as-is.  Use it at your own risk.  Ensure you understand how it works and configure it correctly for your specific needs.  The author is not responsible for any issues or damages caused by using this project.

## Contributing

Contributions are welcome!  Feel free to open issues or submit pull requests.
