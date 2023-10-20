from typing import List
import argparse
import json
import os

from datasets import Dataset

from multi_token.constants import ROLE_ASSISTANT, ROLE_USER


def _convert_convo(convo) -> List:
    msgs = []
    for m in convo:
        msgs.append(
            {
                "role": {"gpt": ROLE_ASSISTANT, "human": ROLE_USER}[m["from"]],
                "content": m["value"],
            }
        )
    return msgs


def main(args):
    def gen(json_fns):
        for json_fn in json_fns:
            with open(json_fn) as f:
                data = json.load(f)
            for row in data:
                img_path = row["image"]
                fn = os.path.join(args.image_folder, img_path)
                if not os.path.exists(fn):
                    print("Skipping", fn)
                    continue
                yield {
                    "id": row["id"],
                    "images": [fn],
                    "messages": _convert_convo(row["conversations"]),
                }

    ds = Dataset.from_generator(
        gen, gen_kwargs={"json_fns": args.llava_json}, num_proc=len(args.llava_json)
    )
    ds.save_to_disk(args.output_folder)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--llava_json", type=str, action="append")
    parser.add_argument("-f", "--image_folder", type=str)
    parser.add_argument("-o", "--output_folder", type=str)
    args = parser.parse_args()
    main(args)
