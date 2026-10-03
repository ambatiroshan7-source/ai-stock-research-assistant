"""Streamlit interface for fact-based research and cited filing answers."""
import os
import pandas as pd
import streamlit as st
from bedrock import BedrockError
from financial_data import FinancialDataError,normalize_ticker
from rag import RetrievalError
from research import fetch_financial_snapshot,answer_filing,create_report,compare_companies

st.set_page_config(page_title='AI Stock Research Assistant',page_icon='📊',layout='wide')
st.title('AI Stock Research Assistant')
st.caption('Research from financial data and public filings, explained with Amazon Bedrock.')
st.info('Educational research only. No price predictions, guaranteed returns, or BUY/SELL recommendations. Verify all sources.')
@st.cache_data(ttl=3600,show_spinner=False)
def cached_snapshot(ticker):
    return fetch_financial_snapshot(ticker)


with st.sidebar:
    st.header('Research settings')
    mode_label=st.selectbox('Filing retrieval',['Local TF-IDF vectors','Bedrock Knowledge Base'],index=1 if os.getenv('BEDROCK_KNOWLEDGE_BASE_ID') else 0)
    mode='local' if mode_label.startswith('Local') else 'knowledge_base'
    st.caption('Local mode searches downloaded 10-K text. Knowledge Base mode requires a configured, synced AWS resource.')
    st.caption('Quotes may be delayed. Statement periods and currencies can differ. Free API access is limited.')
    if st.button('Clear financial cache'):
        cached_snapshot.clear()
        from financial_data import _CACHE
        _CACHE.clear()
        st.success('Financial cache cleared.')


def money(value,currency='USD'):
    if value is None:
        return 'Unavailable'
    prefix='$' if currency=='USD' else f'{currency or ""} '
    for threshold,suffix in [(1e12,'T'),(1e9,'B'),(1e6,'M')]:
        if abs(value)>=threshold:
            return f'{prefix}{value/threshold:,.2f}{suffix}'
    return f'{prefix}{value:,.2f}'


def show_sources(sources):
    if not sources:
        st.caption('No retrieved filing sources.')
    for i,source in enumerate(sources,1):
        with st.expander(f'[{i}] {source["ticker"]} 10-K · filed {source["filing_date"]}'):
            url=source.get('source_url','')
            if url.startswith('https://www.sec.gov/'):
                st.link_button('Open original SEC filing',url)
            else:
                st.text(url)
            st.caption(f'Chunk: {source["chunk_id"]} · retrieval score: {source["score"]:.3f}')
            st.write(source['text'])


def show_result(result):
    st.markdown(result['answer'])
    for warning in result.get('warnings',[]):
        st.warning(warning)
    show_sources(result.get('sources',[]))


research_tab,qa_tab,comparison_tab=st.tabs(['Company research','Filing Q&A','Company comparison'])
with research_tab:
    with st.form('analyze'):
        ticker_text=st.text_input('Stock ticker',value='NVDA',max_chars=12)
        submitted=st.form_submit_button('Analyze')
    if submitted:
        try:
            ticker=normalize_ticker(ticker_text)
            with st.spinner('Loading financial facts…'):
                snapshot=cached_snapshot(ticker)
            st.session_state['snapshot']=snapshot
            st.session_state.pop('report',None)
        except ValueError as exc:
            st.error(str(exc))
    snapshot=st.session_state.get('snapshot')
    if snapshot:
        company=snapshot['company']; quote=snapshot['quote']; metrics=snapshot['metrics']
        st.subheader(company.get('name') or snapshot['ticker'])
        st.caption(company.get('industry') or 'Industry unavailable')
        if company.get('description'):
            st.write(company['description'])
        for warning in snapshot['warnings']:
            st.warning(warning)
        cols=st.columns(4)
        currency=company.get('currency','USD')
        cols[0].metric('Recent price',money(quote.get('price'),currency))
        cols[1].metric('Market capitalization',money(company.get('market_cap'),currency))
        cols[2].metric('Revenue (TTM)',money(company.get('revenue_ttm'),currency))
        cols[3].metric('P/E',f'{company["pe"]:.2f}' if company.get('pe') is not None else 'Unavailable')
        rows=[('EPS',company.get('eps'),'Provider EPS'),('Profit margin',company.get('profit_margin'),'Fraction; 0.2 = 20%'),
              ('52-week low',company.get('week_52_low'),currency),('52-week high',company.get('week_52_high'),currency),
              ('Free cash flow',metrics.get('free_cash_flow'),f'Annual: {metrics.get("cash_flow_period") or "unavailable"}'),
              ('Debt',metrics.get('debt'),f'As of: {metrics.get("debt_period") or "unavailable"}')]
        st.dataframe(pd.DataFrame([{'Metric':name,'Value':str(value) if value is not None else 'Unavailable','Period / units':period}
                                 for name,value,period in rows]),hide_index=True,width="stretch")
        st.caption(f'Quote trading date: {quote.get("quote_date") or "unavailable"} · latest company quarter: {company.get("latest_quarter") or "unavailable"} · Source: Alpha Vantage')
        st.caption('Free cash flow = operating cash flow − absolute capital expenditures. Debt is reported debt, not total liabilities.')
        if st.button('Generate AI research report'):
            try:
                with st.spinner('Retrieving evidence and generating the report…'):
                    st.session_state['report']=create_report(snapshot,mode)
            except (BedrockError,RetrievalError,ValueError) as exc:
                st.error(str(exc))
        if 'report' in st.session_state:
            st.subheader('AI research — verify cited evidence')
            show_result(st.session_state['report'])

with qa_tab:
    st.subheader('Ask a filing question')
    st.caption('Local filings: AAPL, MSFT, NVDA. Answers refer to the ingested filing date, not current news.')
    with st.form('filing_question'):
        qa_ticker=st.selectbox('Company',['NVDA','AAPL','MSFT'])
        question=st.text_area('Question',value='What does the company say about competition?',max_chars=2000)
        ask=st.form_submit_button('Ask filing')
    if ask:
        st.session_state.pop('qa',None)
        try:
            with st.spinner('Retrieving passages and asking Bedrock…'):
                st.session_state['qa']=answer_filing(question,qa_ticker,mode)
        except (BedrockError,RetrievalError,ValueError) as exc:
            st.error(str(exc))
    if 'qa' in st.session_state:
        show_result(st.session_state['qa'])
        st.caption(f'Answer time: {st.session_state["qa"]["latency_seconds"]:.2f}s · mode: {st.session_state["qa"]["mode"]}')

with comparison_tab:
    selected=st.multiselect('Companies',['AAPL','MSFT','NVDA','GOOGL','AMZN'],default=['AAPL','MSFT'])
    st.caption('Each uncached company may use four API requests. Free plans can run out quickly.')
    if st.button('Compare financial facts'):
        if len(selected)<2:
            st.warning('Select at least two companies.')
        else:
            with st.spinner('Loading company data…'):
                snapshots=[cached_snapshot(ticker) for ticker in selected]
            st.session_state['comparison_data']=snapshots
            st.session_state.pop('comparison_answer',None)
    if 'comparison_data' in st.session_state:
        snapshots=st.session_state['comparison_data']
        st.dataframe(pd.DataFrame([{'Ticker':row['ticker'],'Currency':row['company'].get('currency'),
                    'Revenue TTM':row['company'].get('revenue_ttm'),'P/E':row['company'].get('pe'),
                    'Market cap':row['company'].get('market_cap'),'Latest quarter':row['company'].get('latest_quarter')}
                   for row in snapshots]),hide_index=True,width="stretch")
        for row in snapshots:
            for warning in row['warnings']:
                st.warning(f'{row["ticker"]}: {warning}')
        if st.button('Explain comparison with Bedrock'):
            try:
                with st.spinner('Generating comparison…'):
                    st.session_state['comparison_answer']=compare_companies(snapshots)
            except (BedrockError,FinancialDataError) as exc:
                st.error(str(exc))
        if 'comparison_answer' in st.session_state:
            st.markdown(st.session_state['comparison_answer'])
