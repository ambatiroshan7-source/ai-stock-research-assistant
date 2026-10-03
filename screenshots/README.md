# Visual previews and screenshots

The two bundled images are rendered previews from actual recorded API values and Bedrock results. They are not screenshots of the live Streamlit interface, and their labels say so explicitly.

- `financial-values-preview.png`: NVDA/MSFT values from the verified local API snapshots, plus a separately verified NVIDIA quote dated October 2, 2026. Missing statement values remain unavailable.
- `filing-answer-preview.png`: the actual managed-retrieval NVIDIA competition answer from `evaluation/results_knowledge_base.json`, including the evaluation note about an unsupported embellishment.

Browser automation failed before capture in this environment. For actual portfolio screenshots, run the app, capture the company overview and filing Q&A with source expanders open, and save `research.png` and `filing-qa.png` here. Avoid including secrets or account identifiers.
