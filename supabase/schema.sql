CREATE TABLE IF NOT EXISTS regions (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  country TEXT NOT NULL,
  sales_manager TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  segment TEXT NOT NULL,
  region_id INTEGER NOT NULL REFERENCES regions(id),
  signup_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  unit_price NUMERIC(12, 2) NOT NULL,
  margin_percent NUMERIC(5, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  order_date DATE NOT NULL,
  quantity INTEGER NOT NULL,
  total_amount NUMERIC(12, 2) NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(id),
  payment_date DATE,
  amount NUMERIC(12, 2) NOT NULL,
  method TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_sessions (
  id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  memory_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS query_runs (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES app_sessions(id),
  question TEXT NOT NULL,
  resolved_question TEXT,
  generated_sql TEXT,
  corrected_sql TEXT,
  final_sql TEXT,
  status TEXT NOT NULL DEFAULT 'pending_review',
  schema_context TEXT,
  historical_context TEXT,
  result_json TEXT,
  chart_json TEXT,
  chart_png_base64 TEXT,
  feedback TEXT,
  error TEXT,
  latency_ms DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO regions (id, name, country, sales_manager) VALUES
  (1, 'North', 'United States', 'Avery Stone'),
  (2, 'South', 'United States', 'Jordan Blake'),
  (3, 'West', 'United States', 'Maya Chen'),
  (4, 'East', 'United States', 'Noah Patel'),
  (5, 'Central', 'United States', 'Riley Morgan')
ON CONFLICT (id) DO NOTHING;

INSERT INTO customers (id, name, email, segment, region_id, signup_date) VALUES
  (1, 'Acme Retail', 'ops@acmeretail.example', 'Enterprise', 1, '2024-01-15'),
  (2, 'Bluebird Foods', 'finance@bluebird.example', 'SMB', 2, '2024-03-07'),
  (3, 'Canyon Outfitters', 'data@canyon.example', 'Mid-Market', 3, '2024-06-21'),
  (4, 'Delta Health', 'analytics@deltahealth.example', 'Enterprise', 4, '2024-08-05'),
  (5, 'Evergreen Supply', 'admin@evergreen.example', 'SMB', 5, '2025-01-12'),
  (6, 'Futura Labs', 'ops@futuralabs.example', 'Startup', 3, '2025-02-03'),
  (7, 'Granite Finance', 'reporting@granite.example', 'Enterprise', 1, '2025-04-14'),
  (8, 'Harbor Logistics', 'bi@harbor.example', 'Mid-Market', 4, '2025-07-30'),
  (9, 'Ion Commerce', 'growth@ion.example', 'Startup', 2, '2025-10-01'),
  (10, 'Juniper Manufacturing', 'planning@juniper.example', 'Mid-Market', 5, '2026-01-18')
ON CONFLICT (id) DO NOTHING;

INSERT INTO products (id, name, category, unit_price, margin_percent) VALUES
  (1, 'Insight Starter', 'Analytics', 99.00, 61.00),
  (2, 'Insight Pro', 'Analytics', 249.00, 68.00),
  (3, 'Workflow Automator', 'Automation', 399.00, 57.00),
  (4, 'Compliance Vault', 'Security', 529.00, 54.00),
  (5, 'Data Sync', 'Integration', 179.00, 63.00),
  (6, 'AI Forecast Pack', 'AI', 699.00, 72.00),
  (7, 'Support Desk Plus', 'Operations', 149.00, 49.00),
  (8, 'Executive Dashboard', 'Analytics', 899.00, 66.00)
ON CONFLICT (id) DO NOTHING;

INSERT INTO orders (id, customer_id, product_id, order_date, quantity, total_amount, status) VALUES
  (1, 1, 8, '2026-01-12', 2, 1798.00, 'paid'),
  (2, 2, 2, '2026-01-24', 4, 996.00, 'paid'),
  (3, 3, 3, '2026-02-09', 3, 1197.00, 'paid'),
  (4, 4, 6, '2026-02-18', 2, 1398.00, 'paid'),
  (5, 5, 5, '2026-03-04', 6, 1074.00, 'pending'),
  (6, 6, 1, '2026-03-21', 9, 891.00, 'paid'),
  (7, 7, 4, '2026-04-08', 2, 1058.00, 'paid'),
  (8, 8, 7, '2026-04-19', 5, 745.00, 'paid'),
  (9, 9, 6, '2026-05-11', 1, 699.00, 'failed'),
  (10, 10, 8, '2026-05-26', 1, 899.00, 'paid'),
  (11, 1, 2, '2026-06-15', 5, 1245.00, 'paid'),
  (12, 2, 3, '2026-06-28', 2, 798.00, 'paid'),
  (13, 3, 6, '2026-07-02', 3, 2097.00, 'paid'),
  (14, 4, 8, '2026-07-22', 1, 899.00, 'paid'),
  (15, 5, 4, '2026-08-06', 2, 1058.00, 'paid'),
  (16, 6, 5, '2026-08-15', 4, 716.00, 'paid'),
  (17, 7, 6, '2026-09-08', 2, 1398.00, 'paid'),
  (18, 8, 2, '2026-09-27', 8, 1992.00, 'paid'),
  (19, 9, 1, '2026-10-03', 7, 693.00, 'paid'),
  (20, 10, 3, '2026-10-11', 3, 1197.00, 'pending'),
  (21, 1, 6, '2026-10-17', 2, 1398.00, 'paid'),
  (22, 3, 8, '2026-10-25', 1, 899.00, 'paid'),
  (23, 4, 5, '2026-10-29', 5, 895.00, 'paid'),
  (24, 8, 4, '2026-11-01', 1, 529.00, 'paid')
ON CONFLICT (id) DO NOTHING;

INSERT INTO payments (id, order_id, payment_date, amount, method, status) VALUES
  (1, 1, '2026-01-13', 1798.00, 'wire', 'paid'),
  (2, 2, '2026-01-25', 996.00, 'card', 'paid'),
  (3, 3, '2026-02-10', 1197.00, 'ach', 'paid'),
  (4, 4, '2026-02-19', 1398.00, 'wire', 'paid'),
  (5, 5, NULL, 1074.00, 'bank_transfer', 'pending'),
  (6, 6, '2026-03-22', 891.00, 'card', 'paid'),
  (7, 7, '2026-04-09', 1058.00, 'wire', 'paid'),
  (8, 8, '2026-04-21', 745.00, 'card', 'paid'),
  (9, 9, NULL, 699.00, 'ach', 'failed'),
  (10, 10, '2026-05-28', 899.00, 'bank_transfer', 'paid'),
  (11, 11, '2026-06-17', 1245.00, 'wire', 'paid'),
  (12, 12, '2026-06-30', 798.00, 'card', 'paid'),
  (13, 13, '2026-07-03', 2097.00, 'wire', 'paid'),
  (14, 14, '2026-07-24', 899.00, 'card', 'paid'),
  (15, 15, '2026-08-08', 1058.00, 'ach', 'paid'),
  (16, 16, '2026-08-17', 716.00, 'card', 'paid'),
  (17, 17, '2026-09-10', 1398.00, 'wire', 'paid'),
  (18, 18, '2026-09-29', 1992.00, 'bank_transfer', 'paid'),
  (19, 19, '2026-10-04', 693.00, 'card', 'paid'),
  (20, 20, NULL, 1197.00, 'wire', 'pending'),
  (21, 21, '2026-10-18', 1398.00, 'wire', 'paid'),
  (22, 22, '2026-10-26', 899.00, 'ach', 'paid'),
  (23, 23, '2026-10-30', 895.00, 'card', 'paid'),
  (24, 24, '2026-11-02', 529.00, 'card', 'paid')
ON CONFLICT (id) DO NOTHING;

