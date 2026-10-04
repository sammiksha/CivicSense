import urllib.request
import json

base_url = 'http://127.0.0.1:8000'

def get(path):
    req = urllib.request.Request(f"{base_url}{path}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def post(path, data):
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

print("Testing /health...")
h = get('/health')
print("Health:", h)

print("\nTesting /api/v1/customers...")
custs = get('/api/v1/customers')
print(f"Loaded {len(custs)} customers.")

product = {
    'product_type': 'ELN',
    'underlying': 'NIFTY 50',
    'tenor_months': 12,
    'coupon_pct': 12,
    'barrier_pct': 70,
    'strike_pct': 100,
    'notional': 1000000,
    'protection_pct': 90,
    'participation_pct': 100
}

print("\nTesting /api/v1/assessment...")
ass = post('/api/v1/assessment', {'product': product, 'customer_id': 'C101', 'mode': 'client'})
print("Assessment decision:", ass.get('status'), "audit_id:", ass.get('audit_id'))

print("\nTesting /api/v1/historical-twin...")
twin = post('/api/v1/historical-twin', {'product': product})
print("Twin found:", twin.get('twin', {}).get('start_date'), "to", twin.get('twin', {}).get('end_date'), "return:", twin.get('twin', {}).get('underlying_return_pct'))

print("\nTesting /api/v1/report/{audit_id}...")
aid = ass.get('audit_id')
pdf_req = urllib.request.Request(f"{base_url}/api/v1/report/{aid}")
with urllib.request.urlopen(pdf_req) as resp:
    pdf_bytes = resp.read()
    print("Report PDF generated, size:", len(pdf_bytes), "bytes")

print("\nTesting /api/v1/copilot...")
cop = post('/api/v1/copilot', {
    'session_id': 'test-session',
    'message': 'What happens if NIFTY falls 35%?',
    'mode': 'client',
    'customer_id': 'C101',
    'product': product
})
print("Copilot response preview:", cop.get('answer', '')[:150])
print("\nALL BACKEND CHECKS PASSED!")
