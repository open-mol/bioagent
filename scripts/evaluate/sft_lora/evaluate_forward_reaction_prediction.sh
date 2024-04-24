#!/bin/bash

# set as environment variables
export HF_HOME="/cto_labs/AIDD/cache"
export MOLECULE_2D_PATH="checkpoints/MoleculeSTM/"

MODEL_VERSION=vicuna-7b-v1.5
TRAIN_VERSION="sft-lora"
EPOCH=0
BASE_LLM_PATH="checkpoints/llava-moleculestm-$MODEL_VERSION-$TRAIN_VERSION/epoch-$EPOCH"
DATA_DIR="/cto_labs/AIDD/DATA/React/MolInstruct/forward_mmchat_smiles/test"
PROJECTOR_DIR="checkpoints/llava-moleculestm-$MODEL_VERSION-stage1/lmm_projector.bin"

# log path
LOG_DIR="./logs/lora/forward_reaction_prediction"

python scripts/evaluate_model.py \
    --model_name_or_path $BASE_LLM_PATH \
    --projectors_path $PROJECTOR_DIR \
    --lora_enable True \
    --dataset_path  $DATA_DIR \
    --max_new_tokens 256 \
    --cache_dir $LOG_DIR \
    --output_dir $LOG_DIR \
    --evaluator "smiles" \
    --verbose \