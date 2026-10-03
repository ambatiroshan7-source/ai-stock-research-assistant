"""Create one private S3 bucket and upload the small filing corpus."""
import json
import os
import uuid
from pathlib import Path
import boto3
from config import Settings
from filings import upload_filings


def prepare_bucket() -> str:
    settings = Settings.from_env()
    session = boto3.Session(profile_name=settings.profile, region_name=settings.region)
    client = session.client('s3')
    bucket = os.getenv('S3_BUCKET', '').strip()
    if not bucket:
        bucket = f'ai-stock-research-{uuid.uuid4().hex[:12]}'
        args = {'Bucket': bucket}
        if settings.region != 'us-east-1':
            args['CreateBucketConfiguration'] = {'LocationConstraint': settings.region}
        client.create_bucket(**args)
        client.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
            'BlockPublicAcls': True, 'IgnorePublicAcls': True,
            'BlockPublicPolicy': True, 'RestrictPublicBuckets': True})
        client.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={
            'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]})
        path = Path(__file__).with_name('.env')
        with path.open('a') as handle:
            handle.write(f'\nS3_BUCKET={bucket}\n')
        os.environ['S3_BUCKET'] = bucket
    else:
        client.head_bucket(Bucket=bucket)
    uploads = upload_filings(bucket)
    objects = client.list_objects_v2(Bucket=bucket).get('Contents', [])
    record = {'bucket': bucket, 'region': settings.region, 'uploaded_objects': uploads,
              'verified_object_count': len(objects)}
    folder = Path(__file__).parent / 'data' / 'private'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'aws_resources.json').write_text(json.dumps(record, indent=2))
    print('Private S3 bucket:', bucket)
    print('Uploaded and verified objects:', len(objects))
    return bucket


if __name__ == '__main__':
    prepare_bucket()
