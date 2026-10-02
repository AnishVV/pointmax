"""JSON export and the last-search file behind `pointmax show N`."""

import json
from pathlib import Path

from pointmax.models import Itinerary
from pointmax.planner.plan import SearchResult


def itineraries_json(its: list[Itinerary]) -> list[dict]:
    return [json.loads(i.model_dump_json()) for i in its]


def export(path: Path, res: SearchResult, ranked: list[Itinerary]) -> None:
    payload = {
        "itineraries": itineraries_json(ranked),
        "rings": [
            {
                "ring": r.ring,
                "gateways": r.gateways,
                "pruned": r.pruned,
                "tasks": r.tasks,
                "best_before": r.best_before,
                "best_after": r.best_after,
                "stopped": r.stopped,
            }
            for r in res.rings
        ],
        "warnings": res.warnings,
        "elapsed_s": round(res.elapsed_s, 1),
    }
    path.write_text(json.dumps(payload, indent=2))


def save_last(path: Path, ranked: list[Itinerary], top: int = 50) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(itineraries_json(ranked[:top])))


def load_last(path: Path) -> list[Itinerary]:
    if not path.exists():
        raise FileNotFoundError("No previous search. Run `pointmax search` first.")
    return [Itinerary.model_validate(d) for d in json.loads(path.read_text())]
