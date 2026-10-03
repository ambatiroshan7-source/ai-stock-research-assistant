import pytest
from bedrock import BedrockError, generate_text, parse_response
from config import Settings


def test_text_blocks():
    assert parse_response({'output': {'message': {'content': [
        {'text': 'First'}, {'toolUse': {}}, {'text': 'Second'}]}}}) == 'First\nSecond'


def test_empty_response():
    with pytest.raises(BedrockError):
        parse_response({})


def test_missing_model_fails_before_aws_call():
    with pytest.raises(BedrockError, match='BEDROCK_MODEL_ID'):
        generate_text('Hello', settings=Settings('us-east-1', None, ''))


def test_converse_request_and_response():
    class FakeClient:
        def converse(self, **kwargs):
            assert kwargs['modelId'] == 'test-model'
            assert kwargs['messages'][0]['content'][0]['text'] == 'Hello'
            return {'output': {'message': {'content': [{'text': 'Answer'}]}}}
    assert generate_text('Hello', settings=Settings('us-east-1', None, 'test-model'), client=FakeClient()) == 'Answer'
