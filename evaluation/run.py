"""Capture real retrieval/answer outputs; never synthesize quality scores."""
import argparse
import csv
import json
import sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research import answer_filing
from bedrock import BedrockError
from rag import RetrievalError

parser=argparse.ArgumentParser()
parser.add_argument('--limit',type=int,default=3)
parser.add_argument('--mode',choices=['local','knowledge_base'],default='local')
args=parser.parse_args()
folder=Path(__file__).parent
rows=list(csv.DictReader((folder/'questions.csv').open()))[:args.limit]
results=[]
for row in rows:
    try:
        result=answer_filing(row['question'],row['ticker'],args.mode)
        result.update(id=row['id'],question=row['question'],ticker=row['ticker'],expected_topics=row['expected_topics'],
                      recorded_at=datetime.now(timezone.utc).isoformat(),manual_review='pending')
        results.append(result)
        print(row['id'],'sources',len(result['sources']),'seconds',round(result['latency_seconds'],2),'warnings',result['warnings'],flush=True)
    except (BedrockError,RetrievalError,ValueError) as exc:
        results.append({**row,'error':str(exc),'manual_review':'not_run'})
        print(row['id'],'FAILED:',str(exc),flush=True)
(folder/f'results_{args.mode}.json').write_text(json.dumps(results,indent=2))
