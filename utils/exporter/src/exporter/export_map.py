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
from utilities.model import Place, Text

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

def _build_feature(place: Place, texts: List[Text]) -> Dict[str, Any]:
    text_data = []
    for t in texts:
        # Aggregate collection flags from all manuscripts witnessing this text
        collections = []
        if any(m.checked_leg for m in t.manuscripts): collections.append("LEG")
        if any(m.checked_dg for m in t.manuscripts):  collections.append("DG")
        if any(m.checked_naso for m in t.manuscripts): collections.append("NASO")

        # Aggregate unique provenance labels and centuries from witnesses
        provenances = sorted(list(set(m.provenance_general_obj.description for m in t.manuscripts if m.provenance_general_obj)))
        centuries   = sorted(list(set(m.dating_century_obj.century for m in t.manuscripts if m.dating_century_obj)))

        # Aggregate modern edition references
        editions = sorted(list(set(e.bibliographic_reference for e in t.editions if e.bibliographic_reference)))

        text_data.append({
            "id":            t.id,
            "bhl":           t.bhl_number,
            "title":         t.title,
            "author":        t.author_obj.name if t.author_obj else None,
            "dating":        t.dating_rough,
            "source_type":   t.source_type.name if t.source_type else None,
            "subtype":       t.subtype.name if t.subtype else None,
            
            "is_reecriture": t.reecriture,
            "arch":          t.origin_archdiocese.name if t.origin_archdiocese else None,
            "bish":          None, # Bishopric normalized into ChurchEntity if needed
            "collections":   collections,
            "provenances":   provenances,
            "centuries":     centuries,
            "edition_refs":  editions,
        })

    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [place.lon, place.lat],
        },
        "properties": {
            "id":         place.id,
            "name":       place.name,
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
        # Get all places with coordinates
        places = session.exec(
            select(Place).where(Place.lat != None, Place.lon != None)
        ).all()

        features: List[Dict[str, Any]] = []
        for p in places:
            # texts relationship is pre-defined in Place
            features.append(_build_feature(p, p.texts))

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    OUTPUT.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Saved: {OUTPUT}")
    logger.info(f"  Features: {len(features)} places with coordinates")


if __name__ == "__main__":
    main()