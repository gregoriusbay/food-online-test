# Coding Test #3: Small vs Large File

## Time & Peak Memory per Section

- 100k: `customers-100000.csv`, loaded at once (coding-1)
- 2M: `customers-2000000.csv`, read in chunks of 50,000 rows (coding-2)
- `(time only)` rows are measured without tracemalloc, because it makes pandas slower
- `read csv` rows in 2M load the whole file at once, only as a comparison

| section                              | peak_mb (100k)   | peak_mb (2M)   | time_s (100k)   |   time_s (2M) |
|:-------------------------------------|:-----------------|:---------------|:----------------|--------------:|
| read csv (time only)                 | -                | -              | 0.5             |         11.27 |
| read csv                             | 54.8             | 1083.2         | 1.16            |         21.14 |
| data quality                         | 13.7             | 69.9           | 0.7             |         97.25 |
| duplicate emails                     | 2.2              | 101.6          | 0.03            |         26.23 |
| country                              | 0.3              | 3.8            | 0.01            |          3.45 |
| country (time only)                  | -                | -              | 0.01            |          3.36 |
| phone patterns                       | 10.7             | 74.2           | 3.58            |         62.7  |
| split phone                          | 33.3             | 151.4          | 3.0             |         66.01 |
| country code by country              | 14.4             | 78.4           | 1.25            |         19.28 |
| subscription date                    | 11.4             | 17.1           | 0.24            |          8.64 |
| email & website                      | 38.7             | 116.4          | 0.98            |         73.65 |
| overview                             | -                | 88.7           | -               |        129    |
| read csv in chunks (time only)       | -                | -              | -               |         10.03 |
| read csv in chunks                   | -                | 50.9           | -               |         23.06 |
| read csv, category dtype (time only) | -                | -              | -               |         10.93 |
| read csv, category dtype             | -                | 1264.6         | -               |         21.73 |

## Chunk Size Experiment (2M file)

|   chunk_size |   n_chunks |   peak_mb |   time_s |
|-------------:|-----------:|----------:|---------:|
|        10000 |        200 |      11.8 |    11.36 |
|        50000 |         40 |      50.9 |    10.27 |
|       200000 |         10 |     198.8 |    10.2  |
|       500000 |          4 |     495.1 |    10.76 |
