#!/bin/bash
# Регистрация первого юзера в Ozon Pro
set -e

cd /home/ozonpro/app

# Создаём JSON файл
cat > /tmp/reg_user.json << JSONEOF
{
  "email": "sasasamarin@gmail.com",
  "password": "OzonPro2026Strong",
  "full_name": "Alex Samarin",
  "company_name": "STOLZ KRAFT"
}
JSONEOF

# Регистрируем
echo "=== Registering user ==="
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d @/tmp/reg_user.json)

echo "$RESPONSE" | python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
    if 'access_token' in d:
        print('✅ User registered successfully!')
        print()
        print('Access Token:')
        print(d['access_token'])
        print()
        print('Refresh Token:')
        print(d['refresh_token'])
    else:
        print('❌ Error:')
        print(json.dumps(d, indent=2, ensure_ascii=False))
except Exception as e:
    print(f'Parse error: {e}')
    print(sys.stdin.read() if sys.stdin else 'no data')
"

# Очищаем JSON
rm -f /tmp/reg_user.json
