import requests
import json
import sqlite3

BASE = 'http://127.0.0.1:8000'

def run_tests():
    # 1. Test Customers
    print('=== 1. Testing Customers API ===')
    r = requests.get(f'{BASE}/api/v1/customers')
    assert r.status_code == 200, f'Status: {r.status_code}'
    custs = r.json()
    print(f'Initial customer count: {len(custs)}')
    for c in custs:
        print(f" - {c['id']}: {c['name']} | Risk: {c['risk_appetite']} | AUM: {c['portfolio_value']}")

    # Test adding new customer
    new_cust = {
        'name': 'Rajiv Sharma',
        'risk_appetite': 'moderate',
        'loss_tolerance_pct': 15.0,
        'horizon_months': 36,
        'portfolio_value': 15000000.0,
        'segment': 'HNI',
        'city': 'Mumbai'
    }
    r_add = requests.post(f'{BASE}/api/v1/customers', json=new_cust)
    print(f"Add customer status: {r_add.status_code}, created: {r_add.json().get('id')}")
    assert r_add.status_code == 200

    r_after = requests.get(f'{BASE}/api/v1/customers')
    print(f'Updated customer count: {len(r_after.json())}')

    # 2. Test Alerts Count and Operations
    print('\n=== 2. Testing Alerts & Notifications API ===')
    r_alerts = requests.get(f'{BASE}/api/v1/customers/all/alerts?unread_only=true')
    alerts_data = r_alerts.json()
    unread_count = alerts_data.get('unread_count', 0)
    print(f'Initial unread count across all clients: {unread_count}')
    assert unread_count > 0, 'Expected at least 1 unread alert'

    first_alert = alerts_data['alerts'][0]
    aid = first_alert['id']
    print(f'Marking single alert #{aid} as read...')
    r_mark = requests.post(f'{BASE}/api/v1/alerts/{aid}/read')
    assert r_mark.status_code == 200

    r_alerts2 = requests.get(f'{BASE}/api/v1/customers/all/alerts?unread_only=true')
    unread_count2 = r_alerts2.json().get('unread_count', 0)
    print(f'Unread count after marking one read: {unread_count2} (expected {unread_count - 1})')
    assert unread_count2 == unread_count - 1

    print('Marking all alerts as read...')
    r_mark_all = requests.post(f'{BASE}/api/v1/alerts/mark-all-read')
    assert r_mark_all.status_code == 200

    r_alerts3 = requests.get(f'{BASE}/api/v1/customers/all/alerts?unread_only=true')
    unread_count3 = r_alerts3.json().get('unread_count', 0)
    print(f'Unread count after marking all read: {unread_count3} (expected 0)')
    assert unread_count3 == 0

    # Reseed alerts for user testing
    conn = sqlite3.connect('structuraai.db')
    conn.execute('UPDATE alerts SET is_read=0')
    conn.commit()
    conn.close()
    r_alerts_reset = requests.get(f'{BASE}/api/v1/customers/all/alerts?unread_only=true')
    reset_count = r_alerts_reset.json().get('unread_count')
    print(f'Alerts re-initialized for user testing: {reset_count} unread')

    # 3. Test Assessment / Simulation endpoint
    print('\n=== 3. Testing Simulator / Assessment API ===')
    test_prod = {
        'product_type': 'ELN',
        'underlying': 'NIFTY 50',
        'barrier_pct': 70.0,
        'strike_pct': 100.0,
        'coupon_pct': 11.8,
        'notional': 1000000.0,
        'tenor_months': 18
    }
    r_assess = requests.post(f'{BASE}/api/v1/assessment', json={'product': test_prod, 'customer_id': 'C101', 'mode': 'rm'})
    print(f'Assessment API status: {r_assess.status_code}')
    res = r_assess.json()
    print(f"Assessment decision: {res.get('status')}")
    print(f"Expected return: {res.get('result', {}).get('metrics', {}).get('expected_return_pct')}%")
    print(f"Breaking point: {res.get('result', {}).get('breaking_point', {}).get('suitable_until_pct')}%")

    print('\nALL VERIFICATION CHECKS PASSED SUCCESSFULLY!')

if __name__ == '__main__':
    run_tests()
