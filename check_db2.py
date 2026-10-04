import sqlite3, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
conn = sqlite3.connect('structuraai.db')
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)
for t in tables:
    if 'customer' in t.lower() or 'profile' in t.lower():
        cols = [d[0] for d in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"\n=== {t} columns: {cols}")
        rows = conn.execute(f"SELECT * FROM {t} LIMIT 3").fetchall()
        for r in rows:
            print(r)
