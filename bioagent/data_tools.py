from typing import Dict, List, Any, Union, Optional
from collections import Counter
from functools import cache
import contextlib
import tempfile
import shutil
import random
import subprocess
import json
import re
import io
import os

import torch
import requests
import transformers
import numpy as np
from datasets import load_dataset, Dataset
from PIL import Image

from bioagent.constants import IGNORE_INDEX


def encode_chat(
    item: Dict,
    tokenizer: transformers.PreTrainedTokenizer,
    modalities: List["Modality"],
) -> Dict:
    messages = list(item["messages"])
    chat_as_string = tokenizer.apply_chat_template(messages, tokenize=False)

    token_to_modality = {m.token: m for m in modalities}
    modality_token_counts = Counter()
    instruct_pattern = r"(\[INST\][\s\S]*?\[\/INST\])"
    pattern = "(" + "|".join(re.escape(m.token) for m in modalities) + ")"

    chat_part = re.split(instruct_pattern, chat_as_string)
    input_ids = []
    labels = []
    for part in chat_part:
        if "[INST]" in part:
            is_instruction = True
        else:
            is_instruction = False
        for subpart in re.split(pattern, part):
            if not subpart:
                continue
            if subpart in token_to_modality:
                assert (
                    is_instruction
                ), "There should be no modality tokens outside of instructions"
                m = token_to_modality[subpart]
                modality_token_counts[m.name] += 1
                input_ids.extend([m.token_idx] * m.token_width)
                labels.extend([IGNORE_INDEX] * m.token_width)
            elif is_instruction:
                part_ids = tokenizer(subpart, add_special_tokens=False).input_ids
                input_ids.extend(part_ids)
                labels.extend([IGNORE_INDEX] * len(part_ids))
            else:
                part_ids = tokenizer(subpart, add_special_tokens=False).input_ids
                input_ids.extend(part_ids)
                labels.extend(part_ids)

    input_ids = torch.tensor(input_ids, dtype=torch.long)
    labels = torch.tensor(labels, dtype=torch.long)

    data_dict = dict(
        input_ids=input_ids,
        labels=labels,
    )
    for m in modalities:
        data_dict[m.name] = m.preprocess_rows([item])[0]
    return data_dict


def parse_chat_output(output: str, style: str = "base") -> Dict:
    if style == "base":
        pattern_thoughts = r"Thoughts:(?:\n| )([\s\S]*?)\n"
        pattern_output = r"Output:(?:\n| )([\s\S]*)"
        thoughts = re.search(pattern_thoughts, output)
        if thoughts:
            thoughts = thoughts.group(1).strip()
        else:
            thoughts = None
        output = re.search(pattern_output, output).group(1).strip()
        return {"output": output, "thoughts": thoughts}
    else:
        raise ValueError(f"Invalid style: {style}")


@contextlib.contextmanager
def with_local_files(fn_or_urls: List[Any]):
    local_fns = []
    fps = []
    for fn_or_url in fn_or_urls:
        if isinstance(fn_or_url, Image.Image):
            fp = tempfile.NamedTemporaryFile(suffix=".png", mode="wb")
            fn_or_url.convert("RGB").save(fp)
            fps.append(fp)
            local_fns.append(fp.name)
        elif fn_or_url.startswith("http://") or fn_or_url.startswith("https://"):
            suffix = os.path.splitext(fn_or_url)[-1]
            with requests.get(fn_or_url, stream=True) as r:
                fp = tempfile.NamedTemporaryFile(suffix=suffix, mode="wb")
                shutil.copyfileobj(r.raw, fp)
                fps.append(fp)
                local_fns.append(fp.name)
        else:
            local_fns.append(fn_or_url)
    try:
        yield local_fns
    finally:
        for fp in fps:
            fp.close()


@cache
def _get_dataset(dataset_args: str) -> Dataset:
    return load_dataset(**json.loads(dataset_args))


def get_dataset_cached(dataset_args: Dict) -> Dataset:
    return _get_dataset(json.dumps(dataset_args))