"""Small, traceable SEC 10-K ingestion pipeline."""
import argparse
import json
import os
import re
import time
from html.parser import HTMLParser
from pathlib import Path

import requests
import boto3
from config import Settings

ROOT = Path(__file__).parent / 'data' / 'filings'
CIKS = {'AAPL': '0000320193', 'MSFT': '0000789019', 'NVDA': '0001045810'}


class FilingError(RuntimeError):
    pass


class FilingTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'ix:header'):
            self.hidden += 1
        if tag in ('p', 'div', 'tr', 'br', 'h1', 'h2', 'h3') and not self.hidden:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'ix:header'):
            self.hidden = max(0, self.hidden - 1)
        if tag in ('p', 'div', 'tr') and not self.hidden:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data + ' ')


def extract_text(html: str) -> str:
    parser = FilingTextParser()
    parser.feed(html)
    text = '\n'.join(re.sub(r'\s+', ' ', line).strip() for line in ''.join(parser.parts).splitlines())
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def sec_get(url: str) -> requests.Response:
    agent = os.getenv('SEC_USER_AGENT', '').strip()
    if not agent or '@' not in agent or 'example.com' in agent:
        raise FilingError('Set SEC_USER_AGENT to your real name and contact email in .env.')
    time.sleep(0.25)
    try:
        response = requests.get(url, headers={'User-Agent': agent, 'Accept-Encoding': 'gzip, deflate'}, timeout=40)
        response.raise_for_status()
        return response
    except requests.RequestException:
        raise FilingError('SEC download failed. Check network, requester identity, and SEC access restrictions.') from None


def download_latest(ticker: str) -> Path:
    if ticker not in CIKS:
        raise FilingError('Filing ingestion supports AAPL, MSFT, and NVDA.')
    try:
        recent = sec_get(f'https://data.sec.gov/submissions/CIK{CIKS[ticker]}.json').json()['filings']['recent']
        indices = [i for i, form in enumerate(recent['form']) if form == '10-K']
        if not indices:
            raise FilingError('No 10-K found in the recent SEC submission history.')
        i = max(indices, key=lambda n: recent['filingDate'][n])
        accession = recent['accessionNumber'][i]
        url = f"https://www.sec.gov/Archives/edgar/data/{int(CIKS[ticker])}/{accession.replace('-', '')}/{recent['primaryDocument'][i]}"
        folder = ROOT / ticker / '10-K'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'{accession}.txt'
        if not path.exists():
            text = extract_text(sec_get(url).text)
            if len(text) < 10000:
                raise FilingError('Downloaded text is unexpectedly short; not using it as a filing.')
            path.write_text(text)
        meta = {'ticker': ticker, 'form': '10-K', 'filing_date': recent['filingDate'][i],
                'report_date': recent['reportDate'][i], 'accession': accession, 'source_url': url}
        path.with_name(path.name + '.metadata.json').write_text(json.dumps({'metadataAttributes': meta}, indent=2))
        return path
    except (KeyError, ValueError, IndexError):
        raise FilingError('Unexpected SEC submission format.') from None


def upload_filings(bucket: str) -> list[str]:
    if not bucket:
        raise FilingError('Set S3_BUCKET before uploading.')
    settings = Settings.from_env()
    client = boto3.Session(profile_name=settings.profile, region_name=settings.region).client('s3')
    uploaded = []
    for path in sorted(ROOT.rglob('*')):
        if path.is_file():
            key = path.relative_to(ROOT).as_posix()
            client.upload_file(str(path), bucket, key, ExtraArgs={'ServerSideEncryption': 'AES256'})
            uploaded.append(f's3://{bucket}/{key}')
    return uploaded


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ticker', choices=CIKS)
    parser.add_argument('--upload', action='store_true')
    args = parser.parse_args()
    try:
        if args.ticker:
            print('Saved', download_latest(args.ticker))
        if args.upload:
            for uri in upload_filings(os.getenv('S3_BUCKET', '')):
                print(uri)
    except FilingError as exc:
        parser.exit(1, str(exc) + '\n')
