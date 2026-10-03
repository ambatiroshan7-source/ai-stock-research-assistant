# Evaluation methodology

`questions.csv` contains 24 questions: seven per company plus three unsupported/unsafe requests. Expected topics are reviewer hints, not gold answers or automatic correctness labels.

## Recorded runs

On October 3, 2026, the first three questions were run against local TF-IDF retrieval and against a real Bedrock Knowledge Base backed by S3 Vectors. Each backend's JSON records the actual generated answer, retrieved text, source URL, filing date, retrieval score, mode, and wall-clock latency. The remaining questions have not been run. Do not report results as a 24-question benchmark.

```sh
python evaluation/run.py --limit 3 --mode local
python evaluation/run.py --limit 3 --mode knowledge_base
```

These commands invoke Bedrock and incur charges. They overwrite the corresponding result file. Preserve a prior run before rerunning if you need comparisons. Model output varies.

## Review rubric

For each question, inspect the cited passages and original filing:

- Retrieval relevance: do passages address the question? Note irrelevant or missing passages.
- Answer correctness: are statements supported by the retrieved text? Distinguish narrow factual support from comprehensive coverage.
- Citation correctness: do citation numbers map to the correct company and passage? Checking number range is automatic; checking claim support requires review.
- Unsupported claims: record embellishments, external knowledge, unsupported calculations, or unsupported forecasts.
- Latency: report actual client-observed seconds, including retrieval and generation. A three-question run is too small to characterize production latency.

`manual_review.csv` records a qualitative review by the coding assistant, not an independent financial expert or blind evaluation. The reviewer compared generated claims with retrieved excerpts; it did not comprehensively audit the full filings or establish ground-truth recall. No numeric correctness, precision, recall, or hallucination rate is claimed.

## Observations

Local Microsoft cybersecurity retrieval emphasized the cybersecurity program and materiality disclosure, missing the more substantive risk passage returned by managed retrieval in this sample. The managed NVIDIA answer added “innovate continuously,” which was not explicit in its cited excerpt. These are reasons to inspect source text even when every citation number is valid.

A separate research-report smoke test revealed mixed reporting periods and numerical repetition. The final report receives deterministic qualitative financial observations and filing excerpts with quantities omitted. A comparison smoke test also misstated revenue; the final comparison uses the same qualitative boundary. Exact metrics remain in the Python-rendered UI. Reports with unexpected numeric output are withheld. This restriction reduces one failure mode; it does not prove factual correctness.

Next evaluation work: run all questions, have an independent reviewer label supporting passages, include explicit abstention tests, compare different chunk sizes, and measure repeatability across model runs. Do not treat the bundled expected topics as complete answers.
