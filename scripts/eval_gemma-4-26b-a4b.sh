#!/bin/bash

cd "$(dirname "$0")/.."

DATA_PATH=./tests/3/data/eval/eval_dataset.json
PROMPT_PATH=./tests/3/eval_prompt.advanced.md

python3 eval.py --endpoint http://localhost:7874/v1/chat/completions --endpoint_type vllm --data_path $DATA_PATH --model_name google/gemma-4-26B-A4B-it --prompt_path $PROMPT_PATH