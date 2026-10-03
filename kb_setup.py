"""Small managed Knowledge Base backed by S3 Vectors; resumable state is local."""
import argparse
import json
import os
import time
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
from config import Settings

STATE = Path(__file__).parent/'data'/'private'/'knowledge_base_resources.json'


def setup():
    settings=Settings.from_env()
    bucket=os.getenv('S3_BUCKET','').strip()
    if not bucket:
        raise RuntimeError('Run aws_setup.py first.')
    session=boto3.Session(profile_name=settings.profile,region_name=settings.region)
    iam=session.client('iam'); vectors=session.client('s3vectors'); agent=session.client('bedrock-agent')
    account=session.client('sts').get_caller_identity()['Account']
    state=json.loads(STATE.read_text()) if STATE.exists() else {'region':settings.region,'document_bucket':bucket}
    def save():
        STATE.parent.mkdir(parents=True,exist_ok=True)
        STATE.write_text(json.dumps(state,indent=2))
    name=bucket.replace('ai-stock-research-','stock-research-vectors-')
    embedding=f'arn:aws:bedrock:{settings.region}::foundation-model/amazon.titan-embed-text-v2:0'
    if 'vector_bucket_arn' not in state:
        state['vector_bucket_arn']=vectors.create_vector_bucket(vectorBucketName=name)['vectorBucketArn']
        state['vector_bucket_name']=name;save()
    if 'index_arn' not in state:
        state['index_arn']=vectors.create_index(vectorBucketName=name,indexName='filings',dataType='float32',
            dimension=1024,distanceMetric='cosine',metadataConfiguration={
                'nonFilterableMetadataKeys':['AMAZON_BEDROCK_TEXT','AMAZON_BEDROCK_METADATA']})['indexArn']
        save()
    role_name='StockResearchKB-'+bucket.rsplit('-',1)[-1]
    trust={'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'Service':'bedrock.amazonaws.com'},
            'Action':'sts:AssumeRole','Condition':{'StringEquals':{'aws:SourceAccount':account},
            'ArnLike':{'aws:SourceArn':f'arn:aws:bedrock:{settings.region}:{account}:knowledge-base/*'}}}]}
    if 'role_arn' not in state:
        state['role_arn']=iam.create_role(RoleName=role_name,AssumeRolePolicyDocument=json.dumps(trust))['Role']['Arn']
        state['role_name']=role_name;save()
        policy={'Version':'2012-10-17','Statement':[
            {'Effect':'Allow','Action':['bedrock:InvokeModel'],'Resource':embedding},
            {'Effect':'Allow','Action':['s3:ListBucket'],'Resource':f'arn:aws:s3:::{bucket}'},
            {'Effect':'Allow','Action':['s3:GetObject'],'Resource':f'arn:aws:s3:::{bucket}/*'},
            {'Effect':'Allow','Action':['s3vectors:PutVectors','s3vectors:GetVectors','s3vectors:DeleteVectors',
                's3vectors:QueryVectors','s3vectors:GetIndex'],'Resource':state['index_arn']},
        ]}
        iam.put_role_policy(RoleName=role_name,PolicyName='FilingIngestion',PolicyDocument=json.dumps(policy))
        time.sleep(10)
    if 'knowledge_base_id' not in state:
        for attempt in range(3):
            try:
                kb=agent.create_knowledge_base(name='StockResearchFilings',roleArn=state['role_arn'],
                    knowledgeBaseConfiguration={'type':'VECTOR','vectorKnowledgeBaseConfiguration':{
                        'embeddingModelArn':embedding,'embeddingModelConfiguration':{
                            'bedrockEmbeddingModelConfiguration':{'dimensions':1024,'embeddingDataType':'FLOAT32'}}}},
                    storageConfiguration={'type':'S3_VECTORS','s3VectorsConfiguration':{
                        'vectorBucketArn':state['vector_bucket_arn'],'indexArn':state['index_arn']}})['knowledgeBase']
                break
            except ClientError as exc:
                if attempt==2 or exc.response['Error']['Code'] not in ('ValidationException','AccessDeniedException'):
                    raise
                time.sleep(10)
        state['knowledge_base_id']=kb['knowledgeBaseId'];save()
        trust['Statement'][0]['Condition']['ArnLike']['aws:SourceArn']=kb['knowledgeBaseArn']
        iam.update_assume_role_policy(RoleName=role_name,PolicyDocument=json.dumps(trust))
    kb_id=state['knowledge_base_id']
    print('Knowledge Base:',kb_id,flush=True)
    for attempt in range(6):
        kb=agent.get_knowledge_base(knowledgeBaseId=kb_id)['knowledgeBase']
        if kb['status']=='ACTIVE':
            break
        if kb['status']=='FAILED':
            raise RuntimeError('Knowledge Base creation failed; inspect failure reasons in the console.')
        time.sleep(5)
    else:
        raise RuntimeError('Knowledge Base is still provisioning. Run setup again shortly.')
    if 'data_source_id' not in state:
        ds=agent.create_data_source(knowledgeBaseId=kb_id,name='Company10KFilings',dataDeletionPolicy='DELETE',
            dataSourceConfiguration={'type':'S3','s3Configuration':{'bucketArn':f'arn:aws:s3:::{bucket}'}},
            vectorIngestionConfiguration={'chunkingConfiguration':{'chunkingStrategy':'FIXED_SIZE',
                'fixedSizeChunkingConfiguration':{'maxTokens':350,'overlapPercentage':15}}})['dataSource']
        state['data_source_id']=ds['dataSourceId'];save()
    if 'ingestion_job_id' not in state:
        job=agent.start_ingestion_job(knowledgeBaseId=kb_id,dataSourceId=state['data_source_id'])['ingestionJob']
        state['ingestion_job_id']=job['ingestionJobId'];save()
    print('Ingestion job:',state['ingestion_job_id'],flush=True)
    return state


def status():
    state=json.loads(STATE.read_text())
    s=Settings.from_env()
    agent=boto3.Session(profile_name=s.profile,region_name=s.region).client('bedrock-agent')
    job=agent.get_ingestion_job(knowledgeBaseId=state['knowledge_base_id'],dataSourceId=state['data_source_id'],
                              ingestionJobId=state['ingestion_job_id'])['ingestionJob']
    print('Ingestion status:',job['status'])
    print('Statistics:',job.get('statistics',{}))
    if job.get('failureReasons'):
        print('Failure reasons:',job['failureReasons'])
    state['ingestion_status']=job['status'];state['ingestion_statistics']=job.get('statistics',{})
    STATE.write_text(json.dumps(state,indent=2))
    if job['status']=='COMPLETE':
        from dotenv import set_key
        set_key(str(Path(__file__).with_name('.env')),'BEDROCK_KNOWLEDGE_BASE_ID',state['knowledge_base_id'])
    return job


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--status',action='store_true');args=parser.parse_args()
    try:
        status() if args.status else setup()
    except ClientError as exc:
        print('AWS setup failed:',exc.response.get('Error',{}).get('Code'))
        print('Inspect local resource state; use local retrieval while resolving AWS setup.')
        raise SystemExit(1)
