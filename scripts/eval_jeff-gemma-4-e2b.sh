#!/bin/bash

cd "$(dirname "$0")/.."

API_KEY=YOUR_API_KEY_HERE
DATA_PATH=./tests/3/data/eval/eval_dataset.json
PROMPT_PATH=./tests/3/eval_prompt.jeff.basic.md

python3 eval.py --endpoint http://localhost:8000/v1/systemone --endpoint_type jeff --api_key $API_KEY --data_path $DATA_PATH --model_name jeff-gemma-4-e2b-it --prompt_path $PROMPT_PATH