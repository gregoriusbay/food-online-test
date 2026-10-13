This repo has my answers for the **Technical AI Engineer Test**. The test is split into two parts:

- **Engineering Knowledge**: 5 theory questions (REST API vs MCP, Docker for AI, finetuning an LLM, etc). The answers are in [knowledge-test/Technical AI Engineer Test.pdf](knowledge-test/Technical%20AI%20Engineer%20Test.pdf).
- **Coding Test**: analysing a small and a large CSV, vector cosine similarity, and a platform to upload online food receipts and ask questions about them with an LLM.

Video of the coding test: [Google Drive](https://drive.google.com/file/d/17y7OmMa8lzAZMAddBD9Ig9BUJKlaE_c3/view?usp=sharing)

## Where each question is

| No | Question | Where |
| --- | --- | --- |
| K1–K5 | Engineering Knowledge | [knowledge-test/Technical AI Engineer Test.pdf](knowledge-test/Technical%20AI%20Engineer%20Test.pdf) |
| C1 | Parse & get insight from `customers-100000.csv` | [data-analytical-test/coding-1.ipynb](data-analytical-test/coding-1.ipynb) |
| C2 | Parse `customers-2000000.csv` with low memory | [data-analytical-test/coding-2.ipynb](data-analytical-test/coding-2.ipynb) |
| C3 | Small vs large file | [data-analytical-test/coding-3.py](data-analytical-test/coding-3.py) + conclusion in coding-2 |
| C4 | Self-hosted vector DB + manual cosine similarity | [docker-compose.yml](docker-compose.yml) (pgvector), [backend/similarity.py](backend/similarity.py) |
| C5a–c | Upload receipt, extract with a vision model, store to DB | [backend/api.py](backend/api.py), [backend/llm.py](backend/llm.py), [backend/extract.py](backend/extract.py), [backend/database.py](backend/database.py), [frontend/](frontend/) |
| C5d | AI tools to answer questions about the receipts | [backend/tools.py](backend/tools.py) |
| C5e | Docker image, running locally | [Dockerfile](Dockerfile), [frontend/.docker/Dockerfile](frontend/.docker/Dockerfile), [docker-compose.yml](docker-compose.yml) |
| C5f | CI/CD | [.gitlab-ci.yml](.gitlab-ci.yml), [ci/](ci/) |

## Folder structure

```
backend/
  api.py          # Flask API: /upload, /receipts, /receipts/<id>, /receipts/<id>/image, /ask
  llm.py          # extraction prompt + schema, Ollama calls (vision & embedding)
  extract.py      # post-processing of the model output (dates, numbers, item names)
  database.py     # save/read receipts in Postgres, plus the queries used by the tools
  tools.py        # tool-calling agent behind /ask
  similarity.py   # cosine similarity + top-k, numpy only
frontend/         # React + Vite + Tailwind (receipt list, detail/correction, ask page)
data/
  schema.sql      # receipts & receipt_items tables (embedding column is vector(768))
  struk_restoran_*.jpg/png/jpeg   # sample receipts to try the upload
  customers-100000.csv
data-analytical-test/
  coding-1.ipynb  # C1
  coding-2.ipynb  # C2
  coding-3.py     # C3, puts the C1 & C2 measurements side by side
ci/               # scripts called from .gitlab-ci.yml (image build, trivy scans)
knowledge-test/   # answers for the Engineering Knowledge part (PDF)
```

## Coding Test 1–3 (CSV)

Done with pandas in Jupyter. The data is synthetic customer data (Customer Id, name, company, city, country, 2 phone numbers, email, subscription date, website).

- **coding-1**: the 100.000 row file is loaded at once, then checked for data quality (missing values, duplicates, unique ratio), country distribution, phone number patterns, subscription dates, email and website domains.
- **coding-2**: same analysis for the 2.000.000 row file, but read in chunks of 50.000 rows and only the aggregates are kept (value counts, 8-byte hashes for unique/duplicate counts). Loading it at once needs about 1,4 GB, with chunks each section peaks at around 4–150 MB. There's also a chunk size experiment (10.000 / 50.000 / 200.000 / 500.000) and a try with the `category` dtype.
- **coding-3**: every section in coding-1 and coding-2 records its time and peak memory (with `tracemalloc`). This script puts them side by side in `coding-3-results.md`.

In short: a small file is fine to load at once, it's fast and you can `groupby` anything right away. A large file has to be read in chunks, so memory stays small and stable, but every analysis has to read the file again from the start (slower), and anything that needs to see all the data at once (unique values, duplicates) needs a workaround, like hashing. More detail in the Conclusion section of each notebook.

To run them:

```bash
pip install pandas numpy jupyter tabulate
```

1. Put `customers-2000000.csv` in `data/` (it's git-ignored because of its size).
2. Change `PATH` in the first cell of the notebooks if your repo is somewhere else, it's still an absolute `D:\personal-project\...` path.
3. Run `coding-1.ipynb` then `coding-2.ipynb` (both write csv files with the measurements).
4. From `data-analytical-test/`, run `python coding-3.py`.

## Coding Test 4 (vector DB + cosine similarity)

The vector DB is self-hosted: Postgres + [pgvector](https://github.com/pgvector/pgvector) (`pgvector/pgvector:pg16` image in docker-compose). Every food item on a receipt is embedded with `nomic-embed-text` (768 dims) and stored in `receipt_items.embedding`.

pgvector is **only used as storage** here, the `<=>` operators etc. are not used on purpose. The ranking is done in [backend/similarity.py](backend/similarity.py):

```
cos(a, b) = (a · b) / (|a| * |b|)
```

`top_k()` computes this for all candidates at once (numpy matrix multiply) and takes the k highest scores. A zero vector gets a score of 0. It's used by the `search_items` tool, e.g. when the user asks about "hamburger" or "sweet drinks".

## Coding Test 5 (food receipt platform)

### Flow

1. User uploads a receipt photo/PDF from the UI (`POST /upload`, max 10 MB, jpg/png/bmp/tif/pdf).
2. The file is rendered to images (PyMuPDF) and sent to the `qwen3-vl:8b-instruct` vision model on Ollama, with a JSON schema so the output is structured: `restaurant`, `purchased_at`, `purchased_time`, `items[]` (`food_name`, `line_total`), `subtotal`, `tax`, `fee`, `discount`, `total_price`.
3. [extract.py](backend/extract.py) cleans it up: date formats (including Indonesian month names), Rupiah amounts, "2x" removed from item names, and a leftover "total" row dropped from the items. It only reformats what's on the receipt, it doesn't add anything of its own.
4. Food names get embedded, then everything is saved to Postgres (what the model read is kept as-is too, in `raw_output`).
5. In the UI the result can be checked and corrected by hand (`PATCH /receipts/<id>`), embeddings are regenerated when item names change. The extraction runs in the background, so you can move to another page while it's working; the receipt shows up in the table when it's done.

### Asking questions (`POST /ask`)

The LLM never touches the DB. It only picks a tool and its arguments, then Python runs the query ([tools.py](backend/tools.py)):

| Tool | Used for |
| --- | --- |
| `list_items` | "what food did I buy yesterday" |
| `spending_summary` | total spending, can be filtered by date / restaurant |
| `spending_by_restaurant` | total per restaurant |
| `search_items` | search food by meaning (vector search + the cosine above) |
| `list_receipts` / `get_receipt` | list receipts / one receipt in detail |

The example questions from the test:

- "What food did i buy yesterday" → `list_items` with yesterday's range
- "Give me total expenses for food on 20 June" → `spending_summary` with start=end=20 June
- "Where did i buy hamburger from last 7 day" → `search_items` with text="hamburger" + last 7 days range

Relative date ranges (yesterday, last 7 days, last month, etc) are computed in Python first and put in the system prompt, because an 8B model often gets them wrong when it has to calculate them itself. Max 6 tool-call rounds per question. The `/ask` response also returns `tool_calls`, so you can see which tools were called.

### Requirements

- Docker + Docker Compose
- [Ollama](https://ollama.com) running on the host (not in a container, the models are big):

```bash
ollama pull qwen3-vl:8b-instruct
ollama pull nomic-embed-text
```

On CPU, extracting one receipt can take a few minutes, that's why the gunicorn timeout is 900 seconds.

### Run with Docker

Copy the example env in the root (docker-compose reads it for the `db` and `backend` services):

```bash
cp .env.example .env
```

Then:

```bash
docker compose up --build
```

The UI is on **http://localhost:8080**. Nginx in the frontend container forwards `/api/*` to the backend. `data/schema.sql` runs automatically the first time the DB volume is created, so if you change the schema, remove the volume first (`docker compose down -v`).

The backend looks for Ollama at `http://host.docker.internal:11434`, you can change it with `OLLAMA_HOST`.

### Try it

In the UI (http://localhost:8080):

1. **Extract** → **Extract receipt**, pick one of the sample receipts in `data/` (`struk_restoran_*`). The modal closes and an "Extracting…" row shows in the table. On CPU this takes a few minutes, you can go to another page meanwhile.
2. When it's done the receipt shows up in the table. Click it: the image is on the left, the extracted fields and items on the right. Change something and press **Save**, reload the page to see it was stored.
3. The **JSON** tab shows the same data as JSON, with Copy and Download.
4. **Ask** → try the example questions from the test, e.g. "Where did i buy hamburger from last 7 day". Keep in mind the dates come from the receipts, so "yesterday" or "last 7 days" only finds something if a receipt has a date in that range.

Or with curl, through the same nginx (`/api/...`):

```bash
curl -F "file=@data/struk_restoran_1.jpg" http://localhost:8080/api/upload
curl http://localhost:8080/api/receipts
curl -X POST http://localhost:8080/api/ask -H "Content-Type: application/json" \
  -d '{"question": "Where did i buy hamburger from last 7 day"}'
```

To look at the tables directly (DBeaver, pgAdmin, psql): host `localhost`, port **5433**, database `postgres`, user `postgres`, password from `.env`. Port 5432 is a different Postgres if you also have one installed on your machine.

### If something doesn't work

- **An upload stays on "Extracting…" for a long time.** Check that Ollama is running on the host (`ollama list`) and that both models are pulled, then look at the backend log: `docker compose logs backend --tail 50`.
- **"Extraction failed" popup.** The message comes from the backend. Most of the time the model didn't return usable JSON (a very blurry photo, or not a receipt); try another image.
- **The table is empty after `docker compose down -v`.** That's expected, `-v` deletes the volumes, so all receipts and uploaded images are gone. `docker compose down` (without `-v`) keeps them.
- **Ask is slow.** Every question needs at least two model calls (pick a tool, then write the answer). On CPU that's often a minute or more.

### Run without Docker (for development)

```bash
# DB still runs in a container, exposed on port 5433
docker compose up db

# backend (port 5000)
pip install -r requirements.txt
cd backend
python api.py

# frontend (port 3000), /api is proxied to the backend
cd frontend
cp .env.example .env
npm install
npm run dev
```

The backend reads the same root `.env` (`DB_HOST=localhost`, `DB_PORT=5433`, `DB_NAME=postgres`). Instead of the separate `DB_*` values you can also set one `DATABASE_URL=postgresql://postgres:secret@localhost:5433/postgres`.

Don't mix the two ways of running when you upload receipts: the backend stores the image path, so a receipt uploaded with `python api.py` (path on your disk) has no image in the Docker version, and the other way around.

In this mode the backend is on port 5000 directly (no `/api` prefix):

```bash
curl -F "file=@data/struk_restoran_1.jpg" http://localhost:5000/upload
curl http://localhost:5000/receipts
curl -X POST http://localhost:5000/ask -H "Content-Type: application/json" \
  -d '{"question": "Where did i buy hamburger from last 7 day"}'
```

### CI/CD

Using GitLab CI ([.gitlab-ci.yml](.gitlab-ci.yml)):

1. **test**: lint with `ruff`, Trivy scan on the Docker config
2. **scan**: secret scan (GitGuardian) + Trivy filesystem scan
3. **build**: build the image from `Dockerfile` and push it to the registry ([ci/build-docker-image.sh](ci/build-docker-image.sh))
4. **post-build-scan**: Trivy scan on the built image
5. **deploy**: staging (`staging` branch) / production (git tag)

## Notes / limitations

- The local 8B model still misreads blurry receipts or unusual layouts sometimes, that's why there's a manual correction page.
- No login yet, all receipts belong to one user.
- `search_items` always returns something even when nothing is really similar (it's a ranking), so the LLM is told to ignore low scores. There's no fixed threshold yet.
- Cosine is computed in Python over every item in the date range. Fine for personal receipt data, but with millions of rows it would need an ANN index.
