#!/usr/bin/env bash
# Runs all 21 self-test suites. No keys, no network, no MongoDB needed (in-memory database, fake providers).
#   pip install -r requirements.txt   then   bash run_tests.sh
set -u
cd "$(dirname "$0")"
export APP_ENCRYPTION_KEY="${APP_ENCRYPTION_KEY:-$(python3 -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())')}"
fail=0
for t in tests/selftest*.py; do
  if python3 "$t" > /tmp/selftest.log 2>&1; then echo "PASS  $t"; else echo "FAIL  $t"; tail -15 /tmp/selftest.log; fail=1; fi
done
exit $fail
