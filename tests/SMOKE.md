# Pre-release smoke test (against staging)

Run these 5 commands before every deploy. If any fails, do not deploy.
~2 minutes.

## 1. Public login page reachable
curl -fsS -o /dev/null -w "%{http_code}\n" \
  https://staging.example.com/auth/login
# expect: 200

## 2. Unauthenticated app1 is blocked
curl -fsS -o /dev/null -w "%{http_code}\n" \
  https://staging.example.com/app1/employees
# expect: 401

## 3. Session login → app1 read works
COOKIE=$(curl -fsS -c - -X POST \
  -d "username=smoke_user&password=smoke_pass" \
  https://staging.example.com/auth/login | grep auth_session | awk '{print $7}')

curl -fsS -H "Cookie: auth_session=$COOKIE" \
  https://staging.example.com/app1/employees
# expect: 200, JSON with "items" key

## 4. Device login → app3 ingest works
TOKEN=$(curl -fsS -X POST -H "Content-Type: application/json" \
  -d '{"username":"smoke_tracker","password":"smoke_pass","device_id":"smoke-phone"}' \
  https://staging.example.com/auth/device-login | jq -r .token)

curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id":"smoke-phone","points":[{"lat":14.6,"lon":120.9,"ts":1700000000,"acc":10}]}' \
  https://staging.example.com/app3/
# expect: {"status":"success",...}

## 5. Device token blocked on app1
curl -fsS -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  https://staging.example.com/app1/employees
# expect: 401
