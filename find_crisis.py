import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
content = open('frontend/index.html', encoding='utf-8').read()
lines = content.splitlines()
# Find the customer stress rendering function
keywords = ['cust-stress', 'custStress', 'renderCustStress', 'runCustStress', 'runCustDashboard', 'CUST_CRISIS', 'custCrisis', 'Crisis', 'crisisData', 'crisisSelect']
matches = [(i+1, l) for i, l in enumerate(lines) if any(k in l for k in keywords)]
for n, l in matches[:80]:
    print(f'{n}: {l[:160]}')
