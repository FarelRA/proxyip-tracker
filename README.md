# Cloudflare proxyIP DNS Updater

This project automatically updates Cloudflare DNS records with the fastest IP addresses found by `iptest.exe`.  It's designed to be run as a scheduled GitHub Actions workflow on a Windows runner.

## How it Works

1. **IP Testing (`testProxyIP.py`):** Downloads a ZIP file containing IP lists, extracts it, combines relevant files based on region and TLS mode, and runs `iptest.exe` to test the IPs, saving the results to `ip.csv`.

2. **IP Filtering (`filterIPs.py`):** Filters the `ip.csv` file to find the top fastest IPs based on network latency.

3. **Cloudflare Update (`cfRecUpdate.py`):** Updates specified Cloudflare DNS records with the filtered IP addresses.  It intelligently updates existing records, creates new ones if needed, and deletes any extra records.

4. **Workflow Automation:** A GitHub Actions workflow (`daily_update.yml`) schedules the entire process to run daily.

## GitHub Setup

1. **Repository:** Clone this repository to your GitHub account.

2. **Workflow Configuration:**
   - In your repository's settings (Settings > Secrets and variables > Actions > Secrets), add a secret named `CLOUDFLARE_API_TOKEN` with your Cloudflare API token.
   - In your repository's settings (Settings > Secrets and variables > Actions > Variables), add the `CLOUDFLARE_ZONE_ID` and `CLOUDFLARE_RECORD_NAME` environment variables with your zone id and record name.

3. **Workflow Dispatch (Optional):** You can manually trigger the workflow from the "Actions" tab of your repository if needed.

## Local Setup

1. **Repository:** Clone this repository with git.

2. **Set Environment Variables:**
   - Set secret variable named `CLOUDFLARE_API_TOKEN` with your Cloudflare API token.
   - Set the `CLOUDFLARE_ZONE_ID` and `CLOUDFLARE_RECORD_NAME` environment variables with your zone id and record name.

3. **Running:** Run `python "Quick Run-All.py"`

## Customization

- **Region and TLS Mode:** Modify the `region`, `tls_mode`, and `port` arguments in `testProxyIP.py` to target specific IP lists.
- **Number of IPs:** Change the `top_n` parameter in `filterIPs.py` to control how many fastest IPs are used for the DNS update.
- **Schedule:** Adjust the `cron` expression in `daily_update.yml` to change the workflow schedule.
- **Proxied Records:** Set the `proxied` argument in `cfRecUpdate.py` to `True` if you want your DNS records to be proxied through Cloudflare.

## Disclaimer

This project is provided as-is.  Use it at your own risk.  Ensure you understand how it works and configure it correctly for your specific needs.  The author is not responsible for any issues or damages caused by using this project.


## Contributing

Contributions are welcome!  Feel free to open issues or submit pull requests.
