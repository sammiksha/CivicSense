import re

with open('frontend/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

patterns = [
    r'function\s+loadCustomer',
    r'function\s+runCust',
    r'function\s+loadCust',
    r'function\s+cust',
    r'function\s+initCustomer',
    r'function\s+onDash',
    r'function\s+onPlay',
    r'function\s+setDash',
    r'function\s+setPlay',
]

with open('fn_lines_utf8.txt', 'w', encoding='utf-8') as out:
    for idx, line in enumerate(lines, 1):
        for p in patterns:
            if re.search(p, line):
                out.write(f"L{idx}: {line.strip()[:120]}\n")
                break
