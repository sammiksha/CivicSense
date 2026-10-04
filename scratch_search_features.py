with open('frontend/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

words = ['replay', 'twin', 'export', 'download', 'pdf', 'product-info', 'historical']
with open('feature_matches.txt', 'w', encoding='utf-8') as out:
    for idx, line in enumerate(lines, 1):
        l_low = line.lower()
        if any(w in l_low for w in words):
            if any(k in l_low for k in ['function ', 'id="', 'class="page', 'btn ']):
                out.write(f"L{idx}: {line.strip()[:130]}\n")
