# Retrieval evaluation: benchmark-v1

- **Run:** 2026-10-25 16:40 UTC
- **Labels:** draft (numbers are provisional until reviewed)
- **Questions:** {'fact': 24, 'multi': 6, 'conflict': 3, 'unanswerable': 4}
- **Corpus:** 16 sources, 1202 chunks
- **Embedding model:** BAAI/bge-small-en-v1.5
- **Chunking:** {'size': 1200, 'overlap': 200, 'min_size': 200, 'min_prose_ratio': 0.2}
- **Hybrid:** RRF k=60, 50 candidates per method

## Overall (answerable questions)

| Mode | hit@5 | hit@10 | mrr@10 | precision@5 | page_recall@10 | source_recall@10 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| semantic | 0.697 | 0.848 | 0.442 | 0.255 | 0.563 | 0.745 | 24 | 58 |
| keyword | 0.606 | 0.788 | 0.401 | 0.200 | 0.490 | 0.664 | 27 | 57 |
| hybrid | 0.818 | 0.818 | 0.528 | 0.321 | 0.549 | 0.679 | 57 | 123 |

## By question type (hit@5 / source_recall@10)

| Mode | conflict | fact | multi |
|---|---|---|---|
| semantic | 0.33 / 0.53 | 0.75 / 0.88 | 0.67 / 0.33 |
| keyword | 0.33 / 0.19 | 0.71 / 0.83 | 0.33 / 0.22 |
| hybrid | 1.00 / 0.31 | 0.79 / 0.79 | 0.83 / 0.42 |

## Misses at 5 (no relevant result in the top 5)

- **semantic:** f02, f11, f14, f20, f22, f24, m02, m03, c01, c03
- **keyword:** f01, f12, f14, f15, f17, f20, f22, m02, m04, m05, m06, c01, c03
- **hybrid:** f01, f15, f17, f20, f22, m03
