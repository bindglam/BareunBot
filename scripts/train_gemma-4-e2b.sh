#!/usr/bin/env bash
# 아고라 검열 모델 — Gemma 4 E2B 풀파인튜닝 (GB10 도커)
#
#   scripts/train_gemma-4-e2b.sh pilot        → 1스텝만 돌려서 경로 확인
#   scripts/train_gemma-4-e2b.sh              → 본 학습 (LR 기본 2e-5)
#   LR=1e-5 scripts/train_gemma-4-e2b.sh      → 학습률만 바꿔서
#   SEED=1 RUN=agora-e2b-r2-s1 scripts/train_gemma-4-e2b.sh   → 섞는 순서만 바꿔서 (같은 설정 반복 → 흔들림 크기 재기)
#
# 설정 근거
#   - 2e-5 : jeff 저장소가 Gemma(E2B)에 쓴 학습률 (scripts의 g4 줄)
#   - 64 / 10 : 7,551건 ÷ 64 ≈ 118스텝, 채점 11번 (DATASET.md 6장)
#   - 16 / 4096 : 프롬프트 최대 226토큰 → 16개가 4096 안에 들어감
#   - 모델은 서버 공유 캐시 /home/gogamza/.cache/huggingface 에 이미 있음 (오프라인으로 실행)
#   - embed_tokens_per_layer 는 decoder.py 가 자동으로 동결
set -euo pipefail
cd "$(dirname "$0")/.."

LR="${LR:-2e-5}"
SEED="${SEED:-20260920}"
RUN="${RUN:-agora-e2b-lr${LR}}"
extra=()
if [[ "${1:-}" == "pilot" ]]; then
  RUN="agora-e2b-pilot"
  extra=(--stop-after 1)
  rm -rf "runs/$RUN" "checkpoints/$RUN"
fi

export HF_HOME="${HF_HOME:-/home/gogamza/.cache/huggingface}"   # 서버 공유 캐시 (gemma-4-E2B-it 가 이미 있음)
mkdir -p "runs/$RUN"
exec env HF_HUB_OFFLINE=1 DATA_DIR=data/ scripts/train.sh env HF_HUB_OFFLINE=1 JEFF_EVENTS="runs/$RUN/events.jsonl" PYTHONUNBUFFERED=1 \
  python3 -m jeff.train \
  --train ./data/train.jsonl \
  --development ./data/dev.jsonl \
  --temperature ./data/calibration.jsonl \
  --run "runs/$RUN" --output "checkpoints/$RUN" \
  --base-model google/gemma-4-E2B-it \
  --revision 3e22461f65e89153144f8adb70e3b8c2cc9845a7 \
  --epochs 2 --seed "$SEED" --lr "$LR" --weight-decay 0.01 \
  --batch-size 16 --token-budget 4096 --max-length 1024 \
  --effective-batch-size 64 --eval-every 10 --public-eval-every 1000000 --resume-every 50 \
  --cpu-threads 16 "${extra[@]}"
