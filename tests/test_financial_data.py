import pytest
import financial_data as fd


def test_ticker_validation():
    assert fd.normalize_ticker(' nvda ') == 'NVDA'
    for value in ('', '../secret', 'AAPL&apikey=x', '123'):
        with pytest.raises(ValueError):
            fd.normalize_ticker(value)


def test_missing_and_nonfinite_numbers():
    for value in (None, 'None', '-', 'NaN', 'inf'):
        assert fd.number(value) is None
    assert fd.number('123.45') == 123.45


def test_quote_date_and_price():
    data = fd.parse_quote({'Global Quote': {'05. price': '42', '07. latest trading day': '2026-10-02'}}, 'AAPL')
    assert data['price'] == 42
    assert data['quote_date'] == '2026-10-02'


def test_overview_missing_metrics():
    data = fd.parse_company({'Name': 'Test company', 'PERatio': 'None'}, 'AAPL')
    assert data['pe'] is None
    assert data['revenue_ttm'] is None


def test_cash_flow_and_debt_preserve_periods(monkeypatch):
    monkeypatch.setattr(fd, '_fetch', lambda endpoint, ticker: {
        'OVERVIEW': {'Name': 'Test', 'Currency': 'USD'},
        'CASH_FLOW': {'annualReports': [{'reportedCurrency': 'USD', 'fiscalDateEnding': '2025-12-31',
                                       'operatingCashflow': '100', 'capitalExpenditures': '20'}]},
        'BALANCE_SHEET': {'annualReports': [{'reportedCurrency': 'USD', 'fiscalDateEnding': '2025-12-31',
                                           'shortLongTermDebtTotal': '50'}]},
    }[endpoint])
    data = fd.get_financial_metrics('AAPL')
    assert data['free_cash_flow'] == 80
    assert data['debt'] == 50
    assert data['cash_flow_period'] == '2025-12-31'


def test_partial_failure_keeps_overview(monkeypatch):
    def fetch(endpoint, ticker):
        if endpoint == 'OVERVIEW':
            return {'Name': 'Test', 'Currency': 'USD', 'EPS': '2'}
        raise fd.FinancialDataError('Provider unavailable')
    monkeypatch.setattr(fd, '_fetch', fetch)
    data = fd.get_financial_metrics('AAPL')
    assert data['eps'] == 2
    assert data['debt'] is None
    assert len(data['warnings']) == 2
