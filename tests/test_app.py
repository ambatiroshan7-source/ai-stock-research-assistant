from pathlib import Path
from streamlit.testing.v1 import AppTest
import research


def test_ui_research_and_qa(monkeypatch):
    monkeypatch.setattr(research,'fetch_financial_snapshot',lambda ticker:{
        'ticker':ticker,'company':{'name':'Fixture company','currency':'USD','pe':20},
        'quote':{'price':10,'quote_date':'2026-10-02'},'metrics':{},'warnings':[]})
    monkeypatch.setattr(research,'create_report',lambda *a:{'answer':'Fixture report','sources':[],'warnings':[]})
    monkeypatch.setattr(research,'answer_filing',lambda *a:{'answer':'Fixture grounded answer','sources':[],
                        'warnings':[],'latency_seconds':0.1,'mode':'local'})
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=30).run()
    assert not app.exception
    next(b for b in app.button if b.label=='Analyze').click().run()
    assert not app.exception
    assert app.metric[0].value=='$10.00'
    next(b for b in app.button if b.label=='Generate AI research report').click().run()
    assert not app.exception
    assert any(m.value=='Fixture report' for m in app.markdown)
    next(b for b in app.button if b.label=='Ask filing').click().run()
    assert not app.exception
    assert any(m.value=='Fixture grounded answer' for m in app.markdown)
    app.sidebar.button[0].click().run()
    assert not app.exception
