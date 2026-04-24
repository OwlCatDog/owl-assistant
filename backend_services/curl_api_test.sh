#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash curl_api_test.sh
#
# Optional env:
#   BASE_URL=http://127.0.0.1:8080
#   START_TIME="2026-04-24 00:00:00"
#   END_TIME="2026-04-24 23:59:59"
#
# Simulate "public via FRP" auth check in local test:
#   SIMULATE_PUBLIC=true
#   OWL_AUTH_SALT=change_me
#   FRP_PUBLIC_HEADER_NAME=x-owl-via-frp
#   FRP_PUBLIC_HEADER_VALUE=1
#   OWL_AUTH_HEADER_NAME=owl-auth-token
#   OWL_AUTH_WINDOW_SECONDS=120
#
# Optional print tests:
#   RUN_PRINT_TESTS=true
#   TEST_PRINT_TEXT="hello from curl"
#   TEST_PRINT_IMAGE=/absolute/path/to/test.png

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
API_BASE="${BASE_URL%/}/api/v1"
START_TIME="${START_TIME:-$(date +%F) 00:00:00}"
END_TIME="${END_TIME:-$(date +%F) 23:59:59}"

SIMULATE_PUBLIC="${SIMULATE_PUBLIC:-false}"
FRP_PUBLIC_HEADER_NAME="${FRP_PUBLIC_HEADER_NAME:-x-owl-via-frp}"
FRP_PUBLIC_HEADER_VALUE="${FRP_PUBLIC_HEADER_VALUE:-1}"
OWL_AUTH_HEADER_NAME="${OWL_AUTH_HEADER_NAME:-owl-auth-token}"
OWL_AUTH_WINDOW_SECONDS="${OWL_AUTH_WINDOW_SECONDS:-120}"
OWL_AUTH_SALT="${OWL_AUTH_SALT:-}"

RUN_PRINT_TESTS="${RUN_PRINT_TESTS:-false}"
TEST_PRINT_TEXT="${TEST_PRINT_TEXT:-hello from curl}"
TEST_PRINT_IMAGE="${TEST_PRINT_IMAGE:-}"

COMMON_HEADERS=(-H "Content-Type: application/json")

pp() {
  local tmp
  tmp="$(mktemp)"
  cat > "${tmp}"
  if command -v jq >/dev/null 2>&1 && jq . "${tmp}" >/dev/null 2>&1; then
    jq . "${tmp}"
  else
    cat "${tmp}"
  fi
  rm -f "${tmp}"
}

if [[ "${SIMULATE_PUBLIC}" == "true" ]]; then
  if [[ -z "${OWL_AUTH_SALT}" ]]; then
    echo "SIMULATE_PUBLIC=true requires OWL_AUTH_SALT"
    exit 1
  fi
  TIME_WINDOW="$(( $(date +%s) / OWL_AUTH_WINDOW_SECONDS ))"
  OWL_AUTH_TOKEN="$(printf "%s:%s" "${TIME_WINDOW}" "${OWL_AUTH_SALT}" | sha256sum | awk '{print $1}')"
  COMMON_HEADERS+=(
    -H "${FRP_PUBLIC_HEADER_NAME}: ${FRP_PUBLIC_HEADER_VALUE}"
    -H "${OWL_AUTH_HEADER_NAME}: ${OWL_AUTH_TOKEN}"
  )
fi

echo "== 1) healthz =="
curl -sS "${BASE_URL%/}/healthz" | pp
echo

echo "== 2) sensors latest =="
curl -sS "${COMMON_HEADERS[@]}" "${API_BASE}/sensors/latest" | pp
echo

echo "== 3) sensors history (inside) =="
curl -sS "${COMMON_HEADERS[@]}" \
  -X POST "${API_BASE}/sensors/history" \
  -d "{\"sensor\":\"inside\",\"start\":\"${START_TIME}\",\"end\":\"${END_TIME}\"}" | pp
echo

echo "== 4) sensors history (outside) =="
curl -sS "${COMMON_HEADERS[@]}" \
  -X POST "${API_BASE}/sensors/history" \
  -d "{\"sensor\":\"outside\",\"start\":\"${START_TIME}\",\"end\":\"${END_TIME}\"}" | pp
echo

echo "== 5) sensors history (darkin) =="
curl -sS "${COMMON_HEADERS[@]}" \
  -X POST "${API_BASE}/sensors/history" \
  -d "{\"sensor\":\"darkin\",\"start\":\"${START_TIME}\",\"end\":\"${END_TIME}\"}" | pp
echo

echo "== 6) system raw: cpu_temp =="
curl -sS "${COMMON_HEADERS[@]}" \
  -X POST "${API_BASE}/system/raw" \
  -d '{"req":"cpu_temp"}' | pp
echo

echo "== 7) system raw: load_avg =="
curl -sS "${COMMON_HEADERS[@]}" \
  -X POST "${API_BASE}/system/raw" \
  -d '{"req":"load_avg"}' | pp
echo

echo "== 8) system summary =="
curl -sS "${COMMON_HEADERS[@]}" \
  -X POST "${API_BASE}/system/summary" \
  -d '{}' | pp
echo

echo "== 9) printer online =="
curl -sS "${COMMON_HEADERS[@]}" \
  -X POST "${API_BASE}/printer/online" \
  -d '{}' | pp
echo

if [[ "${RUN_PRINT_TESTS}" == "true" ]]; then
  echo "== 10) printer system-ticket (will print) =="
  curl -sS "${COMMON_HEADERS[@]}" \
    -X POST "${API_BASE}/printer/system-ticket" \
    -d '{}' | pp
  echo

  echo "== 11) printer print text (will print) =="
  CURL_PRINT_HEADERS=()
  if [[ "${SIMULATE_PUBLIC}" == "true" ]]; then
    CURL_PRINT_HEADERS+=(
      -H "${FRP_PUBLIC_HEADER_NAME}: ${FRP_PUBLIC_HEADER_VALUE}"
      -H "${OWL_AUTH_HEADER_NAME}: ${OWL_AUTH_TOKEN}"
    )
  fi
  curl -sS "${CURL_PRINT_HEADERS[@]}" \
    -X POST "${API_BASE}/printer/print" \
    --data-urlencode "file=${TEST_PRINT_TEXT}" | pp
  echo

  if [[ -n "${TEST_PRINT_IMAGE}" && -f "${TEST_PRINT_IMAGE}" ]]; then
    echo "== 12) printer print image (will print) =="
    curl -sS "${CURL_PRINT_HEADERS[@]}" \
      -X POST "${API_BASE}/printer/print" \
      -F "file=@${TEST_PRINT_IMAGE}" | pp
    echo
  else
    echo "skip image print: TEST_PRINT_IMAGE is empty or file not found"
  fi
fi

echo "Done."
