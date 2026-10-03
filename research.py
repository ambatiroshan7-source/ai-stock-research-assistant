"""Coordinate facts, retrieval, and Bedrock without letting the LLM create metrics."""
import time
import re
from dataclasses import asdict
from financial_data import FinancialDataError,get_company_info,get_financial_metrics,get_stock_quote,normalize_ticker
from bedrock import generate_text
from rag import retrieve,validate_citations,RetrievalError
from prompts import filing_prompt,research_prompt,comparison_prompt


def fetch_financial_snapshot(ticker: str) -> dict:
    ticker=normalize_ticker(ticker)
    result={'ticker':ticker,'company':{},'quote':{},'metrics':{},'warnings':[]}
    for name,func in [('company',get_company_info),('quote',get_stock_quote),('metrics',get_financial_metrics)]:
        try:
            result[name]=func(ticker)
            if name=='metrics':
                result['warnings'].extend(result[name].get('warnings',[]))
        except FinancialDataError as exc:
            result['warnings'].append(f'{name}: {exc}')
    return result


def answer_filing(question: str,ticker: str,mode: str='local') -> dict:
    start=time.perf_counter()
    passages=retrieve(question,ticker,mode=mode)
    if not passages:
        return {'answer':'No relevant filing passages found. Download the company filing or try a more specific question.',
                'sources':[],'warnings':[],'latency_seconds':time.perf_counter()-start,'mode':mode}
    answer=generate_text(filing_prompt(question,passages))
    warnings=validate_citations(answer,passages)
    if any('outside' in warning for warning in warnings):
        answer='The model returned an invalid citation. This answer was withheld; inspect the sources and retry.'
    return {'answer':answer,'sources':[asdict(p) for p in passages], 'warnings':warnings,
            'latency_seconds':time.perf_counter()-start,'mode':mode}


def create_report(snapshot: dict,mode: str='local') -> dict:
    ticker=snapshot['ticker']
    passages=retrieve('business revenue growth products competition risks developments',ticker,mode=mode,top_k=6)
    if not snapshot.get('company') and not snapshot.get('quote') and not snapshot.get('metrics') and not passages:
        raise RetrievalError('No company data or filings available; cannot create a grounded report.')
    answer=generate_text(research_prompt(snapshot,passages),max_tokens=2400,
        system_rules='Write a qualitative report only. Do not output any numerical values, dates, numbered lists, financial tables, or source appendix. Numerical metrics are already displayed by Python in the UI. Use unnumbered bullets. The only digits permitted are source citations of the form [1], [2], etc. Cite filing claims. Do not associate market metrics with the latest quarter date.')
    answer=re.sub(r'(?m)^\s*\d+[.)]\s+', '- ', answer)
    answer=answer.replace('10-K', 'annual filing')
    warnings=validate_citations(answer,passages) if passages else ['No filing evidence; report is limited to supplied financial data.']
    if re.search(r'\d', re.sub(r'\[\d+\]', '', answer)):
        raise RetrievalError('The model repeated numerical values in the qualitative report. Result withheld to avoid mixing dates or metrics; retry.')
    if any('outside' in warning for warning in warnings):
        raise RetrievalError('The model returned an invalid source citation. Report withheld; retry.')
    return {'answer':answer,'sources':[asdict(p) for p in passages],
            'warnings':warnings,'mode':mode}


def compare_companies(snapshots: list[dict]) -> str:
    if not any(row.get('company') or row.get('metrics') or row.get('quote') for row in snapshots):
        raise FinancialDataError('No financial data available for comparison.')
    answer=generate_text(comparison_prompt(snapshots),max_tokens=2200,
        system_rules='Compare qualitatively only. Exact numbers and dates are already in the Python table. Use unnumbered bullets; do not output numerical quantities, dates, or numerical investment rankings.')
    answer=re.sub(r'(?m)^\s*\d+[.)]\s+', '- ', answer)
    if re.search(r'\d',answer):
        raise FinancialDataError('The comparison included numerical values. It was withheld; use the factual comparison table and retry.')
    return answer
