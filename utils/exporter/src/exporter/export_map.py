"""
export_map.py  –  Hagiographies DB → GeoJSON export for map visualization

Each Origin with coordinates becomes a GeoJSON Feature:
  geometry   : Point [lon, lat]
  properties : name, texts (list), text_count

Output: /data/hagiographies_map.geojson
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from rich.logging import RichHandler
from sqlmodel import Session, select

from utilities.config import DATA_ROOT
from utilities.db import engine
from utilities.model import Origin, CorpusHagio

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

handler = RichHandler(rich_tracebacks=True, markup=True, show_time=True, show_path=True)
logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[handler])
logger = logging.getLogger(__name__)

OUTPUT = Path("/local-map/data/hagiographies_map.geojson")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_feature(origin: Origin, texts: List[CorpusHagio]) -> Dict[str, Any]:
    text_data = []
    for t in texts:
        # Aggregate collection flags from all manuscripts witnessing this text
        collections = []
        if any(w.manuscript.leg for w in t.witnesses if w.manuscript): collections.append("LEG")
        if any(w.manuscript.dg for w in t.witnesses if w.manuscript):  collections.append("DG")
        if any(w.manuscript.naso for w in t.witnesses if w.manuscript): collections.append("NASO")

        # Aggregate unique provenance labels and centuries from witnesses
        provenances = sorted(list(set(w.provenance.name for w in t.witnesses if w.provenance)))
        centuries   = sorted(list(set(w.dating_century for w in t.witnesses if w.dating_century)))

        # Aggregate modern edition references
        editions = sorted(list(set(e.reference.title for e in t.editions if e.reference)))

        text_data.append({
            "id":            t.id,
            "bhl":           t.bhl_number,
            "title":         t.title,
            "author":        t.author,
            "dating":        t.dating_rough,
            "source_type":   t.source_type,
            "subtype":       t.subtype,
            "is_reecriture": t.is_reecriture,
            "arch":          t.archbishopric.name if t.archbishopric else None,
            "bish":          t.bishopric.name if t.bishopric else None,
            "collections":   collections,
            "provenances":   provenances,
            "centuries":     centuries,
            "edition_refs":  editions,
        })

    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [origin.longitude, origin.latitude],
        },
        "properties": {
            "id":         origin.id,
            "name":       origin.name,
            "texts":      text_data,
            "text_count": len(text_data),
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("Hagiographies → GeoJSON map export started...")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with Session(engine, expire_on_commit=False) as session:
        # Get all origins with coordinates
        origins = session.exec(
            select(Origin).where(Origin.latitude != None, Origin.longitude != None)
        ).all()

        features: List[Dict[str, Any]] = []
        for o in origins:
            # texts relationship is pre-defined in SQLModel
            features.append(_build_feature(o, o.texts))

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    OUTPUT.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Saved: {OUTPUT}")
    logger.info(f"  Features: {len(features)} origins with coordinates")


if __name__ == "__main__":
    main()
