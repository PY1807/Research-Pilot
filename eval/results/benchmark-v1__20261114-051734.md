# Retrieval evaluation: benchmark-v1

- **Run:** 2026-11-14 05:17 UTC
- **Labels:** draft (numbers are provisional until reviewed)
- **Questions:** {'fact': 24, 'multi': 6, 'conflict': 3, 'unanswerable': 4}
- **Corpus:** 16 sources, 1198 chunks
- **Embedding model:** BAAI/bge-small-en-v1.5
- **Chunking:** {'size': 1200, 'overlap': 200, 'min_size': 200, 'min_prose_ratio': 0.2}
- **Hybrid:** RRF k=60, 50 candidates per method
- **Rerank:** Xenova/ms-marco-MiniLM-L-6-v2 over the top 30 hybrid results

## Overall (answerable questions)

| Mode | hit@5 | hit@10 | mrr@10 | precision@5 | page_recall@10 | source_recall@10 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| semantic | 0.697 | 0.848 | 0.444 | 0.255 | 0.563 | 0.745 | 92 | 181 |
| keyword | 0.576 | 0.758 | 0.374 | 0.194 | 0.462 | 0.634 | 43 | 87 |
| hybrid | 0.788 | 0.848 | 0.500 | 0.315 | 0.559 | 0.710 | 117 | 189 |
| rerank | 0.848 | 0.970 | 0.693 | 0.345 | 0.676 | 0.838 | 6489 | 8538 |

## By question type (hit@5 / source_recall@10)

| Mode | conflict | fact | multi |
|---|---|---|---|
| semantic | 0.33 / 0.53 | 0.75 / 0.88 | 0.67 / 0.33 |
| keyword | 0.00 / 0.19 | 0.71 / 0.79 | 0.33 / 0.22 |
| hybrid | 1.00 / 0.31 | 0.79 / 0.83 | 0.67 / 0.42 |
| rerank | 0.67 / 0.42 | 0.83 / 0.96 | 1.00 / 0.57 |

## Misses at 5 (no relevant result in the top 5)

- **semantic:** f02, f11, f14, f20, f22, f24, m02, m03, c01, c03
- **keyword:** f01, f12, f14, f15, f17, f20, f22, m02, m04, m05, m06, c01, c02, c03
- **hybrid:** f01, f15, f17, f20, f22, m02, m03
- **rerank:** f15, f17, f20, f22, c01
