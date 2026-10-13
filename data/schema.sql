CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector, hanya sebagai PENYIMPANAN

CREATE TABLE receipts (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant      varchar(255),
    purchased_at    date,                        -- DARI STRUK, bukan now(); NULL = perlu review
    purchased_time  time,                        -- jam di struk; NULL = tidak tercetak / gagal dibaca
    subtotal        numeric(14,2),
    tax             numeric(14,2),
    fee             numeric(14,2),               -- ongkir + biaya layanan/kemasan/aplikasi + tip
    discount        numeric(14,2),
    total_price     numeric(14,2),               -- yang benar-benar dibayar
    image_path      text NOT NULL,
    raw_output      jsonb,                       -- output mentah VLM
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE receipt_items (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_id  uuid NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    food_name   varchar(255) NOT NULL,
    line_total  numeric(14,2),
    embedding   vector(768)                      -- dimensi = model embedding (nomic-embed-text = 768)
);

CREATE INDEX ON receipts (purchased_at);
CREATE INDEX ON receipt_items (receipt_id);
