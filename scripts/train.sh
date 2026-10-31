#!/usr/bin/env bash
# jeff 학습 컨테이너 실행 (DGX Spark / GB10)
#
#   scripts/train.sh                 → 컨테이너 안에서 bash
#   scripts/train.sh <명령>           → 그 명령만 실행하고 종료
#
# 환경변수
#   HF_HOME   호스트의 값을 그대로 씁니다. 없으면 서버 공유 캐시 /home/gogamza/.cache/huggingface
#             컨테이너 안에서도 '같은 경로'로 마운트하므로 경로가 어긋나지 않습니다.
#   IMAGE     기본 jeff-gb10:1
#   DATA_DIR  학습 데이터 폴더(호스트 경로). 지정하면 컨테이너의 /workspace/data 자리에 마운트합니다.
#             코드가 쓰는 data/... 상대 경로가 모두 이 폴더를 가리킵니다. 미설정 시 저장소의 data/ 를 그대로 씁니다.
#
# 컨테이너는 내 uid 로 돕니다. 이미지 안에는 uid 1000(ubuntu)만 있어서 다른 계정(1001…)은 이름·홈이 없고,
# 그러면 transformers·torch 의 getpass.getuser() 가 KeyError 로 죽습니다 → USER·HOME 을 넘겨 막습니다.
#
# 예)
#   scripts/train.sh python3 -c 'import torch; print(torch.cuda.is_available())'
#   scripts/train.sh jeff-train --help
#   DATA_DIR=../data scripts/train.sh bash
set -euo pipefail
# 상대 경로 DATA_DIR 은 cd 하기 전, 실행한 위치 기준으로 풀어 둡니다
if [[ -n "${DATA_DIR:-}" ]]; then
  if [[ ! -d "$DATA_DIR" ]]; then
    echo "DATA_DIR 경로가 없습니다: $DATA_DIR" >&2
    exit 1
  fi
  DATA_DIR="$(cd "$DATA_DIR" && pwd)"
fi
cd "$(dirname "$0")/.."
REPO="$(pwd)"
IMAGE="${IMAGE:-jeff:1}"

# 호스트의 HF_HOME 을 그대로 사용 (미설정 시 표준 기본값)
HF_HOME="${HF_HOME:-/home/gogamza/.cache/huggingface}"
# 다른 계정은 상위 폴더(/home/gogamza)를 못 볼 수 있으니, 들여다볼 수 있을 때만 확인합니다.
# 마운트는 도커 데몬(root)이 하므로, 캐시 폴더 자체가 읽기 가능(755)이면 컨테이너 안에서는 읽힙니다.
if [[ -x "$(dirname "$HF_HOME")" && ! -d "$HF_HOME" ]]; then
  echo "HF_HOME 경로가 없습니다: $HF_HOME" >&2
  exit 1
fi

# 터미널이면 -it, 아니면 -i 만 (파이프·heredoc 입력이 컨테이너로 전달되도록)
TTY_FLAGS=(-i)
[[ -t 0 && -t 1 ]] && TTY_FLAGS=(-it)

# 저장소 마운트 위에 data/ 만 덮어씁니다
DATA_FLAGS=()
[[ -n "${DATA_DIR:-}" ]] && DATA_FLAGS=(-v "$DATA_DIR:/workspace/data")

exec docker run --rm "${TTY_FLAGS[@]}" \
  --gpus all \
  --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
  -v "$REPO:/workspace" \
  "${DATA_FLAGS[@]}" \
  -v "$HF_HOME:$HF_HOME" \
  -w /workspace \
  -e HF_HOME="$HF_HOME" \
  -e PYTHONPATH=/workspace/jeff/src \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  --user "$(id -u):$(id -g)" \
  -e USER="$(id -un)" -e HOME=/tmp \
  "$IMAGE" "${@:-bash}"
