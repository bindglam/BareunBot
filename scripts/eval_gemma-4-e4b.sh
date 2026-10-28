#!/bin/bash

cd "$(dirname "$0")/.."

DATA_PATH=./tests/2/data/eval/eval_dataset.json
PROMPT_PATH=./tests/2/eval_prompt.basic.md

python3 eval.py --endpoint http://localhost:7875/v1/chat/completions --endpoint_type vllm --data_path $DATA_PATH --model_name google/gemma-4-E4B-it --prompt_path $PROMPT_PATH