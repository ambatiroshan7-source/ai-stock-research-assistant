import pytest
from rag import Passage,chunk_text,rank_passages,retrieve,validate_citations
from prompts import filing_prompt,research_prompt
from filings import extract_text


def p(text, ticker='NVDA'):
    return Passage(text,'https://www.sec.gov/example',ticker,'2026-02-25','test:1')


def test_rank_relevant_passage():
    result=rank_passages('competition risks',[p('Revenue increased.'),p('Competition risks include pricing pressure.')])
    assert 'Competition' in result[0].text
    assert rank_passages('unfindableterm',[p('Revenue increased.')]) == []


def test_chunk_overlap():
    chunks=chunk_text(' '.join(str(i) for i in range(12)),size=6,overlap=2)
    assert chunks[0].split()[-2:] == chunks[1].split()[:2]
    with pytest.raises(ValueError):
        chunk_text('text',size=2,overlap=2)


def test_citation_validation():
    assert validate_citations('Claim [1].',[p('Evidence')]) == []
    assert validate_citations('Claim [2].',[p('Evidence')])
    assert validate_citations('Uncited.',[p('Evidence')])


def test_prompt_evidence_and_limits():
    prompt=filing_prompt('What are risks?',[p('Competition.')])
    assert '[1] NVDA 10-K filed 2026-02-25' in prompt
    assert 'untrusted evidence' in prompt
    assert 'enough evidence' in prompt
    assert 'FINANCIAL FACTS' in research_prompt({'ticker':'NVDA','company':{}},[])


def test_html_excludes_scripts_and_ix_header():
    text=extract_text('<p>Business</p><script>ignore</script><ix:header>hidden</ix:header><p>Risk</p>')
    assert 'Business' in text and 'Risk' in text
    assert 'ignore' not in text and 'hidden' not in text


def test_kb_enforces_company(monkeypatch):
    monkeypatch.setenv('BEDROCK_KNOWLEDGE_BASE_ID','test')
    class Fake:
        def retrieve(self, **kwargs):
            assert kwargs['retrievalConfiguration']['vectorSearchConfiguration']['filter']['equals']['value']=='NVDA'
            return {'retrievalResults':[{'content':{'text':'Wrong company'},'metadata':{'ticker':'AAPL'}},
                     {'content':{'text':'NVIDIA competition'},'metadata':{'ticker':'NVDA','source_url':'https://www.sec.gov/example'}}]}
    rows=retrieve('competition','NVDA',mode='knowledge_base',client=Fake())
    assert len(rows)==1 and rows[0].ticker=='NVDA'
