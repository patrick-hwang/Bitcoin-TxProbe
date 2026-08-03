import json
import re
from dataclasses import dataclass

@dataclass
class InferenceMetrics:
    groundtruth: list = None
    inference: list = None
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    accuracy: float = 0.0

    def __str__(self):
        d = {"tp": self.tp, "tn": self.tn, "fp": self.fp, "fn": self.fn,
             "precision": round(self.precision, 4), 
             "recall": round(self.recall, 4),
             "accuracy": round(self.accuracy, 4)}
        if self.groundtruth is not None:
            d["groundtruth"] = self.groundtruth
        if self.inference is not None:
            d["inference"] = self.inference
        text = json.dumps(d, indent=2)
        text = re.sub(
            r'\[\s+(\d+(?:,\s+\d+)*)\s+\]',
            lambda m: "[" + ",".join(m.group(1).replace(",", "").split()) + "]",
            text,
        )
        return text

def aggregate_metrics(metrics_list):
    n = len(metrics_list)
    return InferenceMetrics(
        tp=sum(m.tp for m in metrics_list) / n,
        tn=sum(m.tn for m in metrics_list) / n,
        fp=sum(m.fp for m in metrics_list) / n,
        fn=sum(m.fn for m in metrics_list) / n,
        precision=sum(m.precision for m in metrics_list) / n,
        recall=sum(m.recall for m in metrics_list) / n,
        accuracy=sum(m.accuracy for m in metrics_list) / n,
    )
