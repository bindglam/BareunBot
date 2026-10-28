#!/usr/bin/env bash
# 학습한 아고라 검열 모델을 jeff-serve(FastAPI)로 띄웁니다 — GB10 도커, 백그라운드 컨테이너.
#
#   CKPT=checkpoints/agora-e2b-r0/selected agora/serve.sh          → 포트 8000 에
#   CKPT=checkpoints/agora-e2b-r1/selected PORT=8001 NAME=serve-r1 agora/serve.sh
#   ADAPTER=checkpoints/agora-e2b-lora-r16/selected agora/serve.sh   → LoRA 어댑터를 출발점에 합쳐서 (요청 model 은 "agora")
#   agora/serve.sh stop
#
# 호출 예:
#   curl -s localhost:8000/v1/systemone -H 'Content-Type: application/json' -d '{
#     "model": "jeff", "state": "야 너 진짜 ㅅㅂ 왜 그래",
#     "questions": {"block": {"type": "noul", "instructions": "…(build_dataset.py 의 INSTRUCTIONS)…",
#                   "criteria": {"true": "차단: 욕설·비방·모욕이 담긴 글", "false": "통과: 정상 글"}}}}'
#   → {"answers": {"block": {"type": "noul", "noul": 0.99}}}  — noul 값이 P(차단)
#
# 학습과 같은 질문 문구를 써야 학습한 대로 판정합니다 (agora/build_dataset.py 의 QUESTION).
# 메모리: 약 10GB. 26B 교사와 같이 띄워도 되지만 E2B 학습과는 같이 못 씁니다.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${NAME:-agora-serve}"
if [[ "${1:-}" == "stop" ]]; then docker rm -f "$NAME" >/dev/null && echo "꺼짐: $NAME"; exit 0; fi

adapter_env=()
if [[ -n "${ADAPTER:-}" ]]; then        # LoRA 어댑터: 출발점(base)은 어댑터에 적힌 경로에서 찾고, 합쳐서(merged) 띄움
  [[ -f "$ADAPTER/adapter_config.json" ]] || { echo "LoRA 어댑터가 아닙니다: $ADAPTER" >&2; exit 1; }
  base_in="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["adapter"]["base_checkpoint"]["path"])' "$ADAPTER/decision_config.json")"
  CKPT="${base_in#/workspace/}"
  aroot="checkpoints/.serve-adapters/$NAME"
  rm -rf "${aroot:?}" && mkdir -p "$aroot"
  ln -sfn "$(realpath --relative-to="$aroot" "$ADAPTER")" "$aroot/${ADAPTER_NAME:-agora}"
  adapter_env=(-e JEFF_ADAPTERS="$aroot" -e JEFF_ADAPTER_MODE=merged)
  IMAGE="${IMAGE:-jeff-gb10:2}"
  echo "어댑터 ${ADAPTER_NAME:-agora} ← $ADAPTER  (출발점 $CKPT, 요청의 \"model\" 은 \"${ADAPTER_NAME:-agora}\")"
fi
CKPT="${CKPT:?CKPT=checkpoints/<학습 이름>/selected (또는 LoRA 는 ADAPTER=…) 를 지정하세요}"
PORT="${PORT:-8000}"
HF_HOME="${HF_HOME:-/home/gogamza/.cache/huggingface}"
[[ -f "$CKPT/decision_config.json" ]] || { echo "체크포인트가 없습니다: $CKPT" >&2; exit 1; }
CKPT="$(realpath --relative-to="$PWD" "$CKPT")"   # selected 는 심볼릭 링크 → 실제 폴더, 컨테이너에선 /workspace 기준
docker rm -f "$NAME" >/dev/null 2>&1 || true

docker run -d --name "$NAME" --gpus all --ipc=host \
  -p "${BIND:-127.0.0.1}:$PORT:8000" \
  -v "$PWD:/workspace" -v "$HF_HOME:$HF_HOME" -w /workspace \
  -e HF_HOME="$HF_HOME" -e HF_HUB_OFFLINE=1 -e PYTHONPATH=/workspace/jeff/src \
  -e JEFF_CHECKPOINT="$CKPT" -e JEFF_HOST=0.0.0.0 -e PORT=8000 \
  -e JEFF_QUEUE_MS="${JEFF_QUEUE_MS:-2000}" -e JEFF_MAX_TOKENS="${JEFF_MAX_TOKENS:-1024}" \
  ${JEFF_API_KEY:+-e JEFF_API_KEY} "${adapter_env[@]}" \
  --user "$(id -u):$(id -g)" -e USER="$(id -un)" -e HOME=/tmp \
  "${IMAGE:-jeff-gb10:1}" python3 -m jeff.server >/dev/null

echo -n "모델 올리는 중 ($CKPT → localhost:$PORT) "
until curl -sf -m 3 "localhost:$PORT/health" | grep -q '"status": *"ready"'; do
  if [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != true ]]; then
    echo; docker logs --tail 30 "$NAME" >&2; exit 1
  fi
  echo -n "."; sleep 3
done
echo " ✅  http://localhost:$PORT  (플레이그라운드: 브라우저로 열기 · 끄기: agora/serve.sh stop)"
