import psycopg2
from psycopg2.extras import RealDictCursor
import json

conn = psycopg2.connect("postgresql://postgres:LovV7WlIgLceL0SidUFhEjQ6nLPQdCGU@db:5432/langchain_auth")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("SELECT run_id, status, document_path FROM runs ORDER BY created_at DESC LIMIT 10;")
    runs = cur.fetchall()
    print(json.dumps(runs, default=str, indent=2))
