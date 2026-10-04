import sqlite3
conn = sqlite3.connect('structuraai.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", tables)
for t in tables:
    name = t[0]
    rows = conn.execute(f"SELECT * FROM {name} LIMIT 3").fetchall()
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {name} LIMIT 1").description or []]
    print(f"\n=== {name} ===")
    print("Cols:", cols)
    for r in rows:
        print(r)
