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
#   RUN_NEGATIVE_TESTS=true
#   RUN_NEGATIVE_AUTH_TEST=true

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
RUN_NEGATIVE_TESTS="${RUN_NEGATIVE_TESTS:-true}"
RUN_NEGATIVE_AUTH_TEST="${RUN_NEGATIVE_AUTH_TEST:-true}"

COMMON_HEADERS=()
JSON_HEADERS=(-H "Content-Type: application/json")
PUBLIC_HEADERS=()
BAD_PUBLIC_HEADERS=()

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
  PUBLIC_HEADERS+=(
    -H "${FRP_PUBLIC_HEADER_NAME}: ${FRP_PUBLIC_HEADER_VALUE}"
    -H "${OWL_AUTH_HEADER_NAME}: ${OWL_AUTH_TOKEN}"
  )
  BAD_PUBLIC_HEADERS+=(
    -H "${FRP_PUBLIC_HEADER_NAME}: ${FRP_PUBLIC_HEADER_VALUE}"
    -H "${OWL_AUTH_HEADER_NAME}: deadbeef"
  )
fi

run_req() {
  local title="$1"
  local expected_http="$2"
  shift 2

  echo "== ${title} =="
  local out http body
  out="$("$@" -w $'\n__HTTP_STATUS__:%{http_code}')"
  http="$(printf '%s\n' "${out}" | tail -n1 | sed 's/^__HTTP_STATUS__://')"
  body="$(printf '%s\n' "${out}" | sed '$d')"
  echo "HTTP ${http}"
  printf '%s\n' "${body}" | pp
  echo

  if [[ -n "${expected_http}" && "${http}" != "${expected_http}" ]]; then
    echo "ERROR: expected HTTP ${expected_http}, got ${http}"
    exit 1
  fi
}

build_headers() {
  local -n target_ref=$1
  target_ref=()
  target_ref+=("${COMMON_HEADERS[@]}")
}

HEADERS=()
build_headers HEADERS

if [[ "${SIMULATE_PUBLIC}" == "true" ]]; then
  HEADERS+=("${PUBLIC_HEADERS[@]}")
fi

run_req "1) healthz" "200" curl -sS "${BASE_URL%/}/healthz"
run_req "2) sensors latest" "200" curl -sS "${HEADERS[@]}" "${API_BASE}/sensors/latest"

run_req "3) sensors history (sensor=inside)" "200" \
  curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/sensors/history" \
  -d "{\"sensor\":\"inside\",\"start\":\"${START_TIME}\",\"end\":\"${END_TIME}\"}"
run_req "4) sensors history (sensor=outside)" "200" \
  curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/sensors/history" \
  -d "{\"sensor\":\"outside\",\"start\":\"${START_TIME}\",\"end\":\"${END_TIME}\"}"
run_req "5) sensors history (sensor=darkin)" "200" \
  curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/sensors/history" \
  -d "{\"sensor\":\"darkin\",\"start\":\"${START_TIME}\",\"end\":\"${END_TIME}\"}"

run_req "6) sensors history (db=inner_sensor)" "200" \
  curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/sensors/history" \
  -d "{\"db\":\"inner_sensor\",\"start\":\"${START_TIME}\",\"end\":\"${END_TIME}\"}"
run_req "7) sensors history (db=out_sensor)" "200" \
  curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/sensors/history" \
  -d "{\"db\":\"out_sensor\",\"start\":\"${START_TIME}\",\"end\":\"${END_TIME}\"}"
run_req "8) sensors history (db=darkin_sensor)" "200" \
  curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/sensors/history" \
  -d "{\"db\":\"darkin_sensor\",\"start\":\"${START_TIME}\",\"end\":\"${END_TIME}\"}"

RAW_REQS=(cpu_utilization cpu_temp current_ram load_avg general_info cpu_info disk_partitions)
idx=9
for req in "${RAW_REQS[@]}"; do
  run_req "${idx}) system raw: ${req}" "200" \
    curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/system/raw" \
    -d "{\"req\":\"${req}\"}"
  idx=$((idx + 1))
done

run_req "${idx}) system summary" "200" \
  curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/system/summary" -d '{}'
idx=$((idx + 1))

run_req "${idx}) printer online" "200" \
  curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/printer/online" -d '{}'
idx=$((idx + 1))

if [[ "${RUN_PRINT_TESTS}" == "true" ]]; then
  run_req "${idx}) printer system-ticket (will print)" "200" \
    curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/printer/system-ticket" -d '{}'
  idx=$((idx + 1))

  run_req "${idx}) printer print text (will print)" "200" \
    curl -sS "${HEADERS[@]}" -X POST "${API_BASE}/printer/print" --data-urlencode "file=${TEST_PRINT_TEXT}"
  idx=$((idx + 1))

  if [[ -n "${TEST_PRINT_IMAGE}" && -f "${TEST_PRINT_IMAGE}" ]]; then
    run_req "${idx}) printer print image (will print)" "200" \
      curl -sS "${HEADERS[@]}" -X POST "${API_BASE}/printer/print" -F "file=@${TEST_PRINT_IMAGE}"
    idx=$((idx + 1))
  else
    echo "skip image print: TEST_PRINT_IMAGE is empty or file not found"
    echo
  fi
fi

if [[ "${RUN_NEGATIVE_TESTS}" == "true" ]]; then
  run_req "${idx}) negative: system raw unknown req" "400" \
    curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/system/raw" -d '{"req":"unknown_raw"}'
  idx=$((idx + 1))

  run_req "${idx}) negative: sensors history invalid sensor" "400" \
    curl -sS "${HEADERS[@]}" "${JSON_HEADERS[@]}" -X POST "${API_BASE}/sensors/history" \
    -d "{\"sensor\":\"invalid_sensor\",\"start\":\"${START_TIME}\",\"end\":\"${END_TIME}\"}"
  idx=$((idx + 1))
fi

if [[ "${SIMULATE_PUBLIC}" == "true" && "${RUN_NEGATIVE_AUTH_TEST}" == "true" ]]; then
  run_req "${idx}) negative auth: wrong owl-auth-token" "401" \
    curl -sS "${COMMON_HEADERS[@]}" "${BAD_PUBLIC_HEADERS[@]}" "${API_BASE}/sensors/latest"
  idx=$((idx + 1))
fi

echo "Done."
