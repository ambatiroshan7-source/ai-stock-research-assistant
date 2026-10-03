# Explaining this project in an interview

## A short opening

“I built a stock research application with Python and Streamlit. Python fetches financial facts from Alpha Vantage, while a filing pipeline downloads three public SEC 10-Ks and stores extracted text and metadata in a private S3 bucket. A Bedrock Knowledge Base uses Titan embeddings and S3 Vectors to retrieve company-filtered passages. Amazon Nova Lite interprets the evidence through Bedrock's Converse API. Users can inspect citations and original filings. There is also a local TF-IDF retrieval fallback. It is an educational research tool, not a trading signal system.”

Only mention the live validation you actually performed. The recorded sample covers three questions per retrieval mode, not all 24 evaluation questions. Financial statement endpoints were restricted during testing; unavailable metrics are displayed honestly.

## 1. What is Amazon Bedrock?

Bedrock is an AWS service for accessing foundation models and building generative AI applications. I use its Runtime API for text generation and its Knowledge Bases capability for document retrieval. I do not train the foundation model in this project.

## 2. Why did you use Bedrock?

It provides model inference through AWS APIs, integrates with IAM and S3, and lets me use a managed retrieval pipeline. It demonstrates an application using AWS services rather than a standalone chatbot.

## 3. Why did you choose Nova Lite?

I needed a text model for a small summarization and Q&A demo. Nova Lite was available and successfully tested in my account in us-east-1. It supports Converse. I did not run a rigorous comparison proving it is the most accurate or cheapest model; provider availability, task fit, and a simple working integration guided the choice.

## 4. What is RAG?

Retrieval augmented generation first searches a document collection, then sends relevant passages with the user's question to the language model. The passages give the model evidence it can use to answer.

## 5. Why use RAG?

A model's training knowledge is not a reliable source for a particular filing. RAG makes the selected filing available at inference time, allows citations, and lets me update documents without retraining the model. Retrieval can still miss relevant text, and the model can still make mistakes.

## 6. How does the Knowledge Base work?

It reads the text files from S3, splits them into overlapping chunks, invokes Titan Text Embeddings V2 to turn chunks into vectors, and stores them in S3 Vectors. At query time it embeds the question and retrieves similar chunks, filtered by company metadata. I use Retrieve followed by Converse so retrieval and generation remain visible and testable.

## 7. How does your application retrieve documents?

Managed mode calls bedrock-agent-runtime Retrieve with a ticker metadata filter. Local mode uses TF-IDF sparse vectors and cosine similarity over the most recently ingested 10-K for the selected company. Local mode uses word overlap rather than learned semantic embeddings; it is simpler and needs no vector service but can miss paraphrases.

## 8. How do you reduce hallucinations?

The prompt asks the model to answer only from supplied evidence and abstain when evidence is insufficient. The UI shows source text. Citation range checks withhold invalid references. Exact financial numbers are rendered by Python; the qualitative research report and comparison get derived observations, and report passages have quantities omitted. This reduces specific errors but does not guarantee all claims are supported. Valid citation numbers alone do not prove correctness.

## 9. How do you evaluate RAG?

I created 24 questions and recorded real outputs for a three-question sample in each retrieval mode. I reviewed retrieved relevance, factual support, citation mapping, unsupported claims, and measured latency. The review found incomplete coverage in the local Microsoft answer and a small unsupported embellishment in the managed NVIDIA answer. I would next build independently labeled ground-truth passages and evaluate the full set.

## 10. Why not ask the LLM to calculate financial metrics?

LLMs can use stale numbers, mishandle units, or mix reporting periods. Python gives reproducible calculations from API values. Free cash flow is operating cash flow minus the magnitude of capital expenditures; the fiscal date stays attached. Missing source values produce a missing result.

## 11. How did you secure credentials?

I used the standard AWS SDK credential provider chain and a local aws login profile with temporary credentials. Keys and requester contact information stay in an ignored .env file. The Knowledge Base service role is scoped to its embedding model, document bucket, vector index, and specific Knowledge Base trust relationship. My personal development login can have broader account permissions; it is not a production least-privilege identity. Deployment should use an application role with only InvokeModel and Retrieve permissions, not a root login.

## 12. How would you scale it?

Keep the managed retrieval service, deploy the UI behind authentication, separate ingestion from requests, cache market data centrally, limit requests, and use an appropriate provider plan. Add tenant authorization if documents ever become private. The current app is a local single-user demo.

## 13. How would you reduce latency?

Cache stable company facts, reuse clients and indexes, retrieve fewer but better passages, keep prompts short, and consider streaming responses. Measure first: the current sample is too small to predict production performance.

## 14. How would you reduce cost?

Avoid resyncing unchanged filings, bound output tokens and retrieved context, cache repeat questions where appropriate, and track invocation usage. S3 Vectors avoids introducing a continuously running database for this small project, but storage, embedding, retrieval, and inference still incur charges.

## 15. What would you improve in version two?

Add section-aware chunking, independent evaluation labels, more filings with freshness controls, financial period alignment, claim-level citation verification, and a secure deployment using a limited IAM role. Improve retrieval before increasing model complexity.

## 16. Biggest challenges?

Connecting browser login to temporary SDK credentials, handling free API restrictions, waiting for asynchronous Knowledge Base provisioning, retrieving the right risk passages, and preventing the report from combining numbers with different dates. I tested those boundaries and documented the remaining limits.

## 17. What if Bedrock returns an incorrect answer?

The UI directs the user to verify sources. Invalid citation numbers are withheld; uncited answers are flagged. Incorrect but well-formatted answers can still pass these checks, so human review is required. I would record the failure as an evaluation case, inspect retrieval versus generation, and improve the relevant component rather than assume a stronger prompt solves everything.

## 18. How would you monitor production?

Track API error categories, latency, throttling, token usage, and spend using application metrics and AWS monitoring. Record retrieval identifiers and prompt/model versions while keeping secrets and unnecessary personal data out of logs. Add periodic evaluation and alerts for ingestion failure or stale data. These production monitoring features are proposed, not implemented in the MVP.

## Explain the code path

- `financial_data.py`: validates tickers, fetches API data, normalizes missing values, preserves financial periods, and caches responses.
- `filings.py`: obtains recent SEC submissions, picks a 10-K, extracts text, and writes source metadata.
- `aws_setup.py` and `kb_setup.py`: create the small AWS document and retrieval resources.
- `rag.py`: retrieves company-specific passages and checks numbered citation ranges.
- `prompts.py`: separates evidence from instructions and builds task-specific prompts.
- `bedrock.py`: invokes Converse and parses text while handling AWS errors.
- `research.py`: orchestrates facts, retrieval, generation, and basic output checks.
- `app.py`: presents data, research reports, filing questions, source expanders, and comparisons.
- `evaluation/`: records reproducible questions and actual sampled outputs.
