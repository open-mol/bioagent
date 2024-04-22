import json
import os
import argparse
import random
from typing import List

import selfies as sf
import tiktoken
from datasets import DatasetDict, Dataset

from bioagent.constants import ROLE_ASSISTANT, ROLE_USER, ROLE_SYSTEM
from bioagent.chemistry_tools.reaction import multicomponent_smiles_to_list
from bioagent.chemistry_tools.smiles import convert_to_canonical_smiles

MOLECULE_TOKEN = "<molecule_2d>"

SYSTEM_PROMPT = """You are a chemist. Now you are given a reaction equation. Please predict the possible solvents of the reaction. The reaction equation has the following format:
```
reactant1.reactant2. ... .reactantN>>product
```
Your task is to predict the <REP_1> representation of the solvents. We provide the <REP_2> of the reactions."""

FEW_SHOT_PROMPT = """Here are some examples of reaction equations."""


PROMPT_TEMPLATES = [
    {
        "input": "<MOLECULE> Based on the given chemical reaction, can you propose some likely solvents that might have been utilized?",
        "output": "A possible solvent can be <OUTPUT> .",
    },
    {
        "input": "Based on the given chemical reaction <MOLECULE>, suggest some possible solvents.",
        "output": "The solvent can be <OUTPUT> .",
    },
    {
        "input": "Can you provide potential solvents for the following chemical reaction? <MOLECULE>",
        "output": "<OUTPUT> .",
    },
    {
        "input": "Can you suggest some solvents that might have been used in the given chemical reaction? <MOLECULE>",
        "output": "A probable solvent could be <OUTPUT> .",
    },
    {
        "input": "<MOLECULE> From the provided chemical reaction, propose some possible solvents that could have been used.",
        "output": "<OUTPUT> .",
    },
    {
        "input": "Given the following chemical reaction <MOLECULE>, what are some potential solvents that could have been employed?",
        "output": "<OUTPUT> .",
    },
    {
        "input": "Given the following reaction <MOLECULE>, what are some possible solvents that could have been utilized?",
        "output": "<OUTPUT> .",
    },
    {
        "input": "Given this chemical reaction <MOLECULE>, what are some solvents that could have been used?",
        "output": "<OUTPUT> .",
    },
    {
        "input": "<MOLECULE> Please propose potential solvents that might have been utilized in the provided chemical reaction.",
        "output": "Sure. A potential answer could be: <OUTPUT> .",
    },
    {
        "input": "Please provide possible solvents based on the following chemical reaction <MOLECULE>.",
        "output": "<OUTPUT> .",
    },
    {
        "input": "Please suggest some possible solvents that could have been used in the following chemical reaction <MOLECULE>.",
        "output": "<OUTPUT> .",
    },
    {
        "input": "What solvents could have been utilized in the following chemical reaction? <MOLECULE>",
        "output": "<OUTPUT> .",
    },
]


def smiles_to_selfies(smiles):
    try:
        selfies = sf.encoder(smiles)
    except Exception as e:
        print(f"Failed to encode {smiles} with error {e}, back to canonical smiles.")
        selfies = smiles
    return selfies

def process_reaction_equation(reaction, format = "smiles", token=True)->List[str]:
    smiles_list = multicomponent_smiles_to_list(reaction)
    smiles_list = [convert_to_canonical_smiles(smi) for smi in smiles_list]
    selfies_list = [smiles_to_selfies(smi) for smi in smiles_list]
    if token:
        molecules = ".".join([MOLECULE_TOKEN for _ in range(len(smiles_list))])
    elif format == "smiles":
        molecules = ".".join(smiles_list)
    elif format == "selfies":
        molecules = ".".join(selfies_list)
    else:
        raise ValueError(f"Unsupported molecule format: {format}")
    
    return selfies_list, smiles_list, molecules

def conversation_train(id, reactants, products, output, format = "smiles", token=True):
    react_selfies_list, react_smiles_list, react_molecules = process_reaction_equation(reactants, format, token)
    prod_selfies_list, prod_smiles_list, prod_molecules = process_reaction_equation(products, format, token)
    selfies_list = react_selfies_list + prod_selfies_list
    smiles_list = react_smiles_list + prod_smiles_list
    _, _, output = process_reaction_equation(output, format, False)
    prompt_template = random.choice(PROMPT_TEMPLATES)
    input_template = prompt_template["input"].replace("<MOLECULE>", react_molecules+">>"+prod_molecules)
    output_template = prompt_template["output"].replace("<OUTPUT>", output)
    system_prompt = SYSTEM_PROMPT.replace("<REP_1>", "structure" if token else format.upper()).replace("<REP_2>", format.upper())
    
    return {
        "id": id,
        "molecules": {"selfies": selfies_list, "smiles": smiles_list},
        "messages": [
            {
                "role": ROLE_SYSTEM,
                "content": system_prompt
            },
            {
                "role": ROLE_USER,
                "content": input_template
            },
            {
                "role": ROLE_ASSISTANT,
                "content": output_template
            }
        ],
    }

def conversation_test(id, reactants, products, output, few_shots: list = None, format = "smiles", token=True):
    react_selfies_list, react_smiles_list, react_molecules = process_reaction_equation(reactants, format, token)
    prod_selfies_list, prod_smiles_list, prod_molecules = process_reaction_equation(products, format, token)
    selfies_list = react_selfies_list + prod_selfies_list
    smiles_list = react_smiles_list + prod_smiles_list
    _, _, output = process_reaction_equation(output, format, False)
    prompt_template = random.choice(PROMPT_TEMPLATES)
    input_template = prompt_template["input"].replace("<MOLECULE>", react_molecules+">>"+prod_molecules)
    output_template = prompt_template["output"].replace("<OUTPUT>", output)
    system_prompt = SYSTEM_PROMPT.replace("<REP_1>", "structure" if token else format.upper()).replace("<REP_2>", format.upper())
    
    if not few_shots:
        content = input_template
    else:
        few_shot_examples = "\n".join(
            f"Few-shot example {i+1}: reaction:{example['input']}, solvents:{example['output']}" for i, example in enumerate(few_shots)
        )
        content = FEW_SHOT_PROMPT + "\n" + few_shot_examples + "\n" + input_template
        
    return {
        "id": id,
        "molecules": {"selfies": selfies_list, "smiles": smiles_list},
        "ground_truth": output,
        "messages": [
            {
                "role": ROLE_SYSTEM,
                "content": system_prompt
            },
            {
                "role": ROLE_USER,
                "content": content
            }
        ],
    }

def generate_few_shot_examples(rows, num_examples=5):
    if not num_examples:
        return None
    return random.sample(sorted(rows, key=lambda x: random.random()), num_examples)

def main(args):
    tokenizer = tiktoken.get_encoding("cl100k_base")
    data_files = {
        "train": os.path.join(args.data_dir, "train", "solvent.json"),
        "dev": os.path.join(args.data_dir, "dev", "solvent.json"),
        "test": os.path.join(args.data_dir, "test", "solvent.json"),
    }
    dataset = {
        "train": Dataset.from_json(data_files["train"]),
        "dev": Dataset.from_json(data_files["dev"]),
        "test": Dataset.from_json(data_files["test"]),
    }
    
    def gen(split):
        for id, item in enumerate(dataset[split]):
            reactions, solvent = item["canonical_rxn"], item["solvent"]
            reactants, products = reactions.split(">>")
            if split == "train":
                result = conversation_train(id, reactants, products, solvent, format=args.format, token=args.token)
            elif split == "dev":
                result = conversation_test(id, reactants, products, solvent, format=args.format, token=args.token)
            elif split == "test":
                # set num_examples to 0 to disable fs-test
                result = conversation_test(id, reactants, products, solvent,
                                           generate_few_shot_examples(dataset[split], num_examples=args.few_shot), format=args.format, token=args.token)
            yield result

    # Create dataset info dictionary
    dataset_info = {
        "description": "Forward synthesis dataset for MolInstruct",
        "version": "1.0.0",
        "license": "Apache-2.0",
        "splits": {
            "train": {"num_examples": len(dataset["train"])},
            "test": {"num_examples": len(dataset["test"])}
        }
    }

    dataset_dict = {}
    for split in ["train", "dev", "test"]:
        dataset_split = Dataset.from_generator(gen, gen_kwargs={"split": split}, num_proc=args.num_proc)
        dataset_dict[split] = dataset_split
        print(f"{split} size: {len(dataset_dict[split])}\n{split} example: {dataset_dict[split][0]}")

    dataset_info["features"] = dataset_dict["test"].features

    dataset_dict = DatasetDict(dataset_dict, info=dataset_info)
    dataset_dict.save_to_disk(args.out_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, required=True)
    parser.add_argument("--out_dir", type=str, required=True)
    parser.add_argument("--num_proc", type=int, default=1)
    parser.add_argument("--token", type=bool, default=True)
    parser.add_argument("--format", type=str, default="smiles", choices=["smiles", "selfies"])
    parser.add_argument("--few_shot", type=int, default=0, help="Number of few-shot examples, set to 0 to disable fs-test")
    args = parser.parse_args()
    main(args)

# python molecule_build_solvent_prediction.py --data_dir /cto_labs/AIDD/DATA/React/TextReact/RCR/MolIns --out_dir /cto_labs/AIDD/DATA/React/TextReact/RCR/MolIns/sp_mmchat_smiles --num_proc 4