"""Local TF-IDF vector retrieval and optional Bedrock Knowledge Base adapter."""
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from config import Settings
from financial_data import normalize_ticker
from filings import ROOT


class RetrievalError(RuntimeError):
    pass


@dataclass(frozen=True)
class Passage:
    text: str
    source_url: str
    ticker: str
    filing_date: str
    chunk_id: str
    score: float = 0.0


STOPWORDS = set('the a an and or of to in for on with is are was were it its our we as by at from what how does company major mentioned latest filing'.split())


def tokens(text: str) -> list[str]:
    return [word for word in re.findall(r'[a-z0-9]+', text.lower()) if word not in STOPWORDS and len(word) > 1]


def chunk_text(text: str, size: int = 220, overlap: int = 40) -> list[str]:
    if size <= overlap or overlap < 0:
        raise ValueError('Chunk size must exceed nonnegative overlap.')
    words = text.split()
    chunks = []
    for start in range(0, len(words), size - overlap):
        chunks.append(' '.join(words[start:start + size]))
        if start + size >= len(words):
            break
    return chunks


def load_passages(ticker: str, root: Path = ROOT) -> list[Passage]:
    ticker = normalize_ticker(ticker)
    documents = list((root / ticker / '10-K').glob('*.txt'))
    if not documents:
        return []
    candidates = []
    for path in documents:
        metadata_path = path.with_name(path.name + '.metadata.json')
        if not metadata_path.exists():
            continue
        try:
            metadata = json.loads(metadata_path.read_text())['metadataAttributes']
            if metadata.get('ticker') != ticker:
                continue
            candidates.append((metadata.get('filing_date', ''), path, metadata))
        except (ValueError, KeyError):
            raise RetrievalError('Filing metadata is invalid; re-ingest the document.') from None
    if not candidates:
        return []
    _, path, metadata = max(candidates, key=lambda row: row[0])
    return [Passage(text, metadata['source_url'], ticker, metadata['filing_date'], f'{path.stem}:{i}')
            for i, text in enumerate(chunk_text(path.read_text()))]


def rank_passages(question: str, passages: list[Passage], top_k: int = 5) -> list[Passage]:
    query = Counter(tokens(question))
    if not query or not passages:
        return []
    counts = [Counter(tokens(p.text)) for p in passages]
    df = Counter(term for count in counts for term in count)
    idf = {term: math.log((1 + len(counts)) / (1 + freq)) + 1 for term, freq in df.items()}
    def vector(count):
        return {term: (1 + math.log(freq)) * idf[term] for term, freq in count.items() if term in idf}
    q = vector(query)
    norm_q = math.sqrt(sum(value ** 2 for value in q.values()))
    if not norm_q:
        return []
    ranked = []
    for passage, count in zip(passages, counts):
        v = vector(count)
        norm_v = math.sqrt(sum(value ** 2 for value in v.values()))
        score = sum(value * v.get(term, 0) for term, value in q.items()) / (norm_q * norm_v) if norm_v else 0
        if score > 0:
            ranked.append(Passage(passage.text, passage.source_url, passage.ticker, passage.filing_date, passage.chunk_id, score))
    return sorted(ranked, key=lambda p: p.score, reverse=True)[:top_k]


def retrieve(question: str, ticker: str, *, mode: str = 'local', top_k: int = 5, client: Any = None) -> list[Passage]:
    ticker = normalize_ticker(ticker)
    if not question.strip() or len(question) > 2000:
        raise ValueError('Enter a question of 1–2000 characters.')
    if mode == 'local':
        return rank_passages(question, load_passages(ticker), top_k)
    if mode != 'knowledge_base':
        raise ValueError('Unknown retrieval mode.')
    kb_id = os.getenv('BEDROCK_KNOWLEDGE_BASE_ID', '').strip()
    if not kb_id:
        raise RetrievalError('Set BEDROCK_KNOWLEDGE_BASE_ID or select local retrieval.')
    try:
        if client is None:
            s = Settings.from_env()
            client = boto3.Session(profile_name=s.profile, region_name=s.region).client('bedrock-agent-runtime')
        response = client.retrieve(knowledgeBaseId=kb_id, retrievalQuery={'text': question},
            retrievalConfiguration={'vectorSearchConfiguration': {
                'numberOfResults': top_k,
                'filter': {'equals': {'key': 'ticker', 'value': ticker}},
            }})
        passages = []
        for i, row in enumerate(response.get('retrievalResults', [])):
            meta = row.get('metadata', {})
            text = row.get('content', {}).get('text', '')
            if not text or meta.get('ticker') != ticker:
                continue
            source = meta.get('source_url') or row.get('location', {}).get('s3Location', {}).get('uri', '')
            passages.append(Passage(text[:10000], source, ticker, meta.get('filing_date', ''), f'kb:{i}', row.get('score', 0)))
        return passages
    except (ClientError, BotoCoreError):
        raise RetrievalError('Knowledge Base retrieval failed. Check ID, ingestion status, metadata, permissions, and region.') from None


def validate_citations(answer: str, passages: list[Passage]) -> list[str]:
    ids = [int(value) for value in re.findall(r'\[(\d+)\]', answer)]
    warnings = []
    if not ids:
        warnings.append('No numbered citations returned; treat this answer as unverified.')
    if any(value < 1 or value > len(passages) for value in ids):
        warnings.append('The answer contains a citation outside the supplied source list.')
    return warnings
