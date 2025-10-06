# Job Scout Automation 🕵️‍♂️
Automated job scraper for Seek (with JSON-LD fallback) and Indeed RSS. 
Runs on GitHub Actions (cron or manual), writes structured JSON, and emails results.

## Tech
- Python (requests, BeautifulSoup)
- GitHub Actions (cron scheduling, auto-commit)
- SMTP email with GitHub Secrets
- JSON output

## How it works
1) Workflow runs on a schedule.  
2) Script scrapes your Seek search + Indeed RSS.  
3) Saves to `output/jobs.json`, commits to the repo.  
4) Emails you the JSON.

## Local run
```bash
pip install -r requirements.txt
python scraper.py
