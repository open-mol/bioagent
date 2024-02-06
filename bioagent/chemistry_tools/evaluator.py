from abc import ABC, abstractmethod
from typing import List, Dict
from functools import partial

from Levenshtein import distance as lev
import numpy as np
from nltk.translate.bleu_score import sentence_bleu
from nltk.translate.meteor_score import meteor_score
from rouge_score import rouge_scorer
from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import MACCSkeys, AllChem
import selfies as sf

RDLogger.DisableLog('rdApp.*')


def exact_match(ot_smi, gt_smi):
    m_out = Chem.MolFromSmiles(ot_smi)
    m_gt = Chem.MolFromSmiles(gt_smi)

    try:
        if Chem.MolToInchi(m_out) == Chem.MolToInchi(m_gt):
            return 1
    except:
        pass
    return 0


def maccs_similarity(ot_m, gt_m):
    return DataStructs.FingerprintSimilarity(
        MACCSkeys.GenMACCSKeys(gt_m), 
        MACCSkeys.GenMACCSKeys(ot_m), 
        metric=DataStructs.TanimotoSimilarity
    )

def morgan_similarity(ot_m, gt_m, radius=2):
    return DataStructs.TanimotoSimilarity(
        AllChem.GetMorganFingerprint(gt_m, radius), 
        AllChem.GetMorganFingerprint(ot_m, radius)
    )

def rdk_similarity(ot_m, gt_m):
    return DataStructs.FingerprintSimilarity(
        Chem.RDKFingerprint(gt_m), 
        Chem.RDKFingerprint(ot_m), 
        metric=DataStructs.TanimotoSimilarity
    )


class Evaluator(ABC):

    @abstractmethod
    def build_evaluate_tuple(self, pred, gt):
        pass

    @abstractmethod
    def evaluate(self, predictions, references, metrics: List[str] = None, verbose: bool = False):
        pass


class MoleculeSMILESEvaluator(Evaluator):
    _metric_functions = {
        "levenshtein": lev,
        "exact_match": exact_match,
        "bleu": sentence_bleu,
        "validity": lambda smiles: smiles is not None,
        "maccs_sims": maccs_similarity,
        "morgan_sims": morgan_similarity,
        "rdk_sims": rdk_similarity
    }

    @staticmethod
    def sf_encode(selfies):
        try:
            smiles = sf.decoder(selfies)
            return smiles
        except Exception:
            return None

    @staticmethod
    def convert_to_canonical_smiles(smiles):
        if smiles is None:
            return None
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is not None:
            canonical_smiles = Chem.MolToSmiles(molecule, isomericSmiles=False, canonical=True)
            return canonical_smiles
        else:
            return None

    def build_evaluate_tuple(self, pred, gt):
        pred_smi = self.sf_encode(pred)
        gt_smi = self.sf_encode(gt)
        return self.convert_to_canonical_smiles(pred_smi), self.convert_to_canonical_smiles(gt_smi)

    def evaluate(self, predictions, references, metrics: List[str] = None, verbose: bool = False):
            
        if metrics is None:
            metrics = ["levenshtein", "exact_match", "bleu", "validity", "maccs_sims", "morgan_sims", "rdk_sims"]

        results = {metric: [] for metric in metrics}

        for pred, gt in zip(predictions, references):
            pred, gt = self.build_evaluate_tuple(pred, gt)

            for metric in metrics:
                if pred is None or gt is None:
                    results[metric].append(0)
                    continue
                elif metric == "validity":
                    results[metric].append(self._metric_functions[metric](pred))
                elif metric in ["maccs_sims", "morgan_sims", "rdk_sims"]:
                    results[metric].append(self._metric_functions[metric](Chem.MolFromSmiles(pred), Chem.MolFromSmiles(gt)))
                else:
                    results[metric].append(self._metric_functions[metric](pred, gt))

        if verbose:
            print("Evaluation results:")
            for metric, values in results.items():
                print(f"{metric}: {np.mean(values)}")

        return results


class MoleculeCaptionEvaluator(Evaluator):
    _metric_functions = {
        "bleu-2": partial(sentence_bleu, weights=(0.5, 0.5)),
        "bleu-4": partial(sentence_bleu, weights=(0.25, 0.25, 0.25, 0.25)),
        "rouge-1": rouge_scorer.RougeScorer(['rouge1']).score,
        "rouge-2": rouge_scorer.RougeScorer(['rouge2']).score,
        "rouge-l": rouge_scorer.RougeScorer(['rougeL']).score,
        "meteor": meteor_score,
    }

    def build_evaluate_tuple(self, pred, gt):
        return pred, gt

    def evaluate(self, predictions, references, metrics: List[str] = None, verbose: bool = False):
        if metrics is None:
            metrics = ["bleu-2", "bleu-4", "meteor", "rouge-1", "rouge-2", "rouge-l"]

        results = {metric: [] for metric in metrics}

        for pred, gt in zip(predictions, references):
            pred, gt = self.build_evaluate_tuple(pred, gt)

            for metric in metrics:
                results[metric].append(self._metric_functions[metric]([gt], pred))

        if verbose:
            print("Evaluation results:")
            for metric, values in results.items():
                print(f"{metric}: {np.mean(values)}")

        return results