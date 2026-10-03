import research
from rag import Passage


def test_empty_retrieval_does_not_call_bedrock(monkeypatch):
    monkeypatch.setattr(research,'retrieve',lambda *a,**k:[])
    monkeypatch.setattr(research,'generate_text',lambda *a,**k: (_ for _ in ()).throw(AssertionError('Should not invoke')))
    result=research.answer_filing('unanswerable','NVDA')
    assert result['sources']==[]
    assert 'No relevant' in result['answer']


def test_invalid_citation_withheld(monkeypatch):
    monkeypatch.setattr(research,'retrieve',lambda *a,**k:[Passage('Evidence','https://www.sec.gov/x','NVDA','2026-02-25','1')])
    monkeypatch.setattr(research,'generate_text',lambda *a,**k:'Unsupported claim [8].')
    result=research.answer_filing('Question','NVDA')
    assert 'withheld' in result['answer']
    assert 'Unsupported claim' not in result['answer']


def test_financial_failure_keeps_other_data(monkeypatch):
    monkeypatch.setattr(research,'get_company_info',lambda ticker:{'name':'Test'})
    monkeypatch.setattr(research,'get_stock_quote',lambda ticker: (_ for _ in ()).throw(research.FinancialDataError('Limited')))
    monkeypatch.setattr(research,'get_financial_metrics',lambda ticker:{'eps':1,'warnings':[]})
    result=research.fetch_financial_snapshot('NVDA')
    assert result['company']['name']=='Test'
    assert result['quote']=={}
    assert result['warnings']


def test_report_withholds_numerical_repetition(monkeypatch):
    import pytest
    monkeypatch.setattr(research,'retrieve',lambda *a,**k:[])
    monkeypatch.setattr(research,'generate_text',lambda *a,**k:'Market cap is $100 billion.')
    with pytest.raises(research.RetrievalError,match='numerical'):
        research.create_report({'ticker':'NVDA','company':{'name':'Test'}})


def test_comparison_withholds_invented_numbers(monkeypatch):
    import pytest
    monkeypatch.setattr(research,'generate_text',lambda *a,**k:'Revenue is 12345.')
    with pytest.raises(research.FinancialDataError,match='numerical'):
        research.compare_companies([{'ticker':'NVDA','company':{'name':'Test'}}])


def test_qualitative_prompt_keeps_exact_values_out():
    from prompts import research_prompt,comparison_prompt
    data={'ticker':'NVDA','company':{'name':'Test','revenue_ttm':123456789,'profit_margin':0.42},'quote':{},'metrics':{}}
    assert '123456789' not in research_prompt(data,[])
    assert '0.42' not in comparison_prompt([data])
