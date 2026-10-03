"""Alpha Vantage data with explicit missing values and short-lived caching."""
import math
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests
import config  # Loads the project .env before reading the API key.


class FinancialDataError(RuntimeError):
    pass


_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}


def normalize_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    if not re.fullmatch(r'[A-Z]{1,5}(?:[.-][A-Z]{1,2})?', ticker):
        raise ValueError('Enter a valid US stock ticker, such as AAPL, MSFT, or NVDA.')
    return ticker


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _fetch(endpoint: str, ticker: str) -> dict[str, Any]:
    ticker = normalize_ticker(ticker)
    key = os.getenv('ALPHA_VANTAGE_API_KEY', '').strip()
    if not key:
        raise FinancialDataError('Set ALPHA_VANTAGE_API_KEY in your local .env file.')
    cache_key = (endpoint, ticker)
    cached = _CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < 3600:
        return cached[1]
    try:
        response = requests.get('https://www.alphavantage.co/query', params={
            'function': endpoint, 'symbol': ticker, 'apikey': key,
        }, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise FinancialDataError('Financial API request failed. Check your connection and try again later.') from None
    if not isinstance(payload, dict):
        raise FinancialDataError('Financial API returned an unexpected response.')
    if 'Note' in payload or 'Information' in payload:
        raise FinancialDataError('Provider rate limit or plan restriction reached. Check your API plan and retry later.')
    if 'Error Message' in payload or not payload:
        raise FinancialDataError('No financial data found. Check the ticker and API key.')
    _CACHE[cache_key] = (time.monotonic(), payload)
    return payload


def parse_quote(payload: dict[str, Any], ticker: str) -> dict[str, Any]:
    quote = payload.get('Global Quote') or {}
    if not quote:
        raise FinancialDataError('No quote available for this ticker.')
    return {'ticker': normalize_ticker(ticker), 'price': number(quote.get('05. price')),
            'quote_date': quote.get('07. latest trading day'), 'source': 'Alpha Vantage GLOBAL_QUOTE'}


def parse_company(payload: dict[str, Any], ticker: str) -> dict[str, Any]:
    if not payload.get('Name'):
        raise FinancialDataError('No company overview available for this ticker.')
    fields = {'market_cap': 'MarketCapitalization', 'revenue_ttm': 'RevenueTTM',
              'eps': 'EPS', 'pe': 'PERatio', 'profit_margin': 'ProfitMargin',
              'week_52_high': '52WeekHigh', 'week_52_low': '52WeekLow'}
    return {'ticker': normalize_ticker(ticker), 'name': payload['Name'],
            'industry': payload.get('Industry'), 'description': payload.get('Description'),
            'currency': payload.get('Currency'), 'latest_quarter': payload.get('LatestQuarter'),
            'source': 'Alpha Vantage OVERVIEW',
            **{name: number(payload.get(field)) for name, field in fields.items()}}


def get_stock_quote(ticker: str) -> dict[str, Any]:
    return parse_quote(_fetch('GLOBAL_QUOTE', ticker), ticker)


def get_company_info(ticker: str) -> dict[str, Any]:
    return parse_company(_fetch('OVERVIEW', ticker), ticker)


def get_financial_metrics(ticker: str) -> dict[str, Any]:
    info = get_company_info(ticker)
    result = {key: info[key] for key in ('market_cap', 'revenue_ttm', 'eps', 'pe',
              'profit_margin', 'week_52_high', 'week_52_low', 'currency', 'latest_quarter')}
    result.update(free_cash_flow=None, debt=None, cash_flow_period=None, debt_period=None,
                  warnings=[], fetched_at=datetime.now(timezone.utc).isoformat())
    for endpoint in ('CASH_FLOW', 'BALANCE_SHEET'):
        try:
            reports = _fetch(endpoint, ticker).get('annualReports') or []
            if not reports:
                result['warnings'].append(f'No annual {endpoint} data available.')
                continue
            report = max(reports, key=lambda item: item.get('fiscalDateEnding', ''))
            if report.get('reportedCurrency') != info['currency']:
                result['warnings'].append(f'{endpoint} currency differs from company overview; values omitted.')
                continue
            if endpoint == 'CASH_FLOW':
                operating = number(report.get('operatingCashflow'))
                capex = number(report.get('capitalExpenditures'))
                result['free_cash_flow'] = operating - abs(capex) if operating is not None and capex is not None else None
                result['cash_flow_period'] = report.get('fiscalDateEnding')
            else:
                result['debt'] = number(report.get('shortLongTermDebtTotal'))
                result['debt_period'] = report.get('fiscalDateEnding')
        except FinancialDataError as exc:
            result['warnings'].append(str(exc))
    result['sources'] = ['Alpha Vantage OVERVIEW', 'CASH_FLOW', 'BALANCE_SHEET']
    result['free_cash_flow_definition'] = 'Annual operating cash flow minus absolute capital expenditures; calculated in Python.'
    result['debt_definition'] = 'Reported shortLongTermDebtTotal; not total liabilities.'
    return result
