from fastapi import FastAPI, Depends, Query
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select, col
from sqlalchemy import func
from typing import Optional
import folium
from folium.plugins import MarkerCluster

from .database import get_session
from .models import (
    City, Location, Library, Manuscript, Witness,
    CorpusHagio, Origin, Provenance
)

app = FastAPI(title="Hagiographies Map")


def build_map(
    session: Session,
    origin_name: Optional[str] = None,
    city_name: Optional[str] = None,
    dating: Optional[str] = None,
    show_origins: bool = True,
    show_destinations: bool = True,
    show_manuscripts: bool = True,
    show_lines: bool = False,
) -> str:

    m = folium.Map(location=[48.0, 10.0], zoom_start=5, tiles="CartoDB positron")

    # ── Laag 1: Origine-punten (waar tekst geschreven is) ──────────────────
    if show_origins:
        origin_cluster = MarkerCluster(name="Origines", show=True).add_to(m)

        origin_stmt = (
            select(
                Origin.id,
                Origin.name.label("origin_name"),
                Origin.latitude,
                Origin.longitude,
                func.count(CorpusHagio.id).label("text_count"),
                func.group_concat(CorpusHagio.title, " · ").label("titles"),
                func.group_concat(CorpusHagio.bhl_number, " · ").label("bhl_numbers"),
                func.group_concat(CorpusHagio.author, " · ").label("authors"),
                func.group_concat(CorpusHagio.dating_rough, " · ").label("datings"),
            )
            .join(CorpusHagio, CorpusHagio.origin_id == Origin.id)
            .where(Origin.latitude.isnot(None))
            .where(Origin.longitude.isnot(None))
            .group_by(Origin.id)
        )

        if origin_name:
            origin_stmt = origin_stmt.where(col(Origin.name).contains(origin_name))

        for row in session.exec(origin_stmt).all():
            def truncate(val, n=4):
                if not val:
                    return "—"
                items = list(dict.fromkeys(v for v in val.split(" · ") if v and v != "None"))
                result = " · ".join(items[:n])
                return result + f" <i>(+{len(items)-n})</i>" if len(items) > n else result

            popup_html = f"""
            <div style="font-family:sans-serif; font-size:13px; min-width:280px; max-width:340px">
                <h4 style="margin:0 0 4px 0">✍️ Origine: {row.origin_name}</h4>
                <hr style="margin:6px 0">
                <b>Teksten ({row.text_count})</b><br>
                <table style="width:100%; font-size:12px; border-collapse:collapse">
                    <tr><td style="color:#888;width:80px">Titels</td>
                        <td>{truncate(row.titles, 3)}</td></tr>
                    <tr><td style="color:#888">BHL</td>
                        <td>{truncate(row.bhl_numbers, 5)}</td></tr>
                    <tr><td style="color:#888">Auteurs</td>
                        <td>{truncate(row.authors, 3)}</td></tr>
                    <tr><td style="color:#888">Datering</td>
                        <td>{truncate(row.datings, 3)}</td></tr>
                </table>
            </div>
            """
            folium.CircleMarker(
                location=[row.latitude, row.longitude],
                radius=min(6 + row.text_count * 1.5, 22),
                popup=folium.Popup(popup_html, max_width=360),
                tooltip=f"✍️ {row.origin_name} ({row.text_count} teksten)",
                color="#1a6b1a",
                fill=True,
                fill_color="#2ecc71",
                fill_opacity=0.75,
            ).add_to(origin_cluster)

    # ── Laag 2: Bestemmings-punten ─────────────────────────────────────────
    if show_destinations:
        dest_cluster = MarkerCluster(name="Bestemmingen", show=True).add_to(m)

        dest_stmt = (
            select(
                CorpusHagio.id,
                CorpusHagio.title,
                CorpusHagio.bhl_number,
                CorpusHagio.author,
                CorpusHagio.dating_rough,
                CorpusHagio.primary_destinatary,
                CorpusHagio.destinatary_latitude,
                CorpusHagio.destinatary_longitude,
                Origin.name.label("origin_name"),
                Origin.latitude.label("origin_lat"),
                Origin.longitude.label("origin_lon"),
            )
            .outerjoin(Origin, CorpusHagio.origin_id == Origin.id)
            .where(CorpusHagio.destinatary_latitude.isnot(None))
            .where(CorpusHagio.destinatary_longitude.isnot(None))
        )

        if origin_name:
            dest_stmt = dest_stmt.where(col(Origin.name).contains(origin_name))

        dest_rows = session.exec(dest_stmt).all()

        for row in dest_rows:
            popup_html = f"""
            <div style="font-family:sans-serif; font-size:13px; min-width:260px; max-width:320px">
                <h4 style="margin:0 0 4px 0">📬 {row.primary_destinatary or 'Bestemming'}</h4>
                <hr style="margin:6px 0">
                <b>{row.title or '—'}</b><br>
                BHL: <code>{row.bhl_number}</code><br>
                Auteur: {row.author or '—'}<br>
                Datering: {row.dating_rough or '—'}<br>
                Origine: {row.origin_name or '—'}
            </div>
            """
            folium.CircleMarker(
                location=[row.destinatary_latitude, row.destinatary_longitude],
                radius=8,
                popup=folium.Popup(popup_html, max_width=340),
                tooltip=f"📬 {row.primary_destinatary or '?'} — {row.title or row.bhl_number}",
                color="#8B0000",
                fill=True,
                fill_color="#e74c3c",
                fill_opacity=0.75,
            ).add_to(dest_cluster)

            # Optioneel: lijn tussen origine en bestemming
            if show_lines and row.origin_lat and row.origin_lon:
                folium.PolyLine(
                    locations=[
                        [row.origin_lat, row.origin_lon],
                        [row.destinatary_latitude, row.destinatary_longitude],
                    ],
                    color="#888",
                    weight=1.5,
                    opacity=0.5,
                    tooltip=f"{row.origin_name} → {row.primary_destinatary}",
                ).add_to(m)

    # ── Laag 3: Manuscripten (fysieke bewaarplaats) ────────────────────────
    if show_manuscripts:
        ms_cluster = MarkerCluster(name="Manuscripten", show=False).add_to(m)

        ms_stmt = (
            select(
                City.name.label("city_name"),
                Library.name.label("library_name"),
                Location.shelfmark,
                func.count(Witness.id).label("witness_count"),
                func.group_concat(CorpusHagio.title, " · ").label("titles"),
                func.group_concat(CorpusHagio.bhl_number, " · ").label("bhl_numbers"),
                func.group_concat(Witness.dating, " · ").label("datings"),
            )
            .join(Location, Manuscript.location_id == Location.id)
            .join(City, Location.city_id == City.id)
            .join(Library, Location.library_id == Library.id)
            .join(Witness, Witness.manuscript_id == Manuscript.id)
            .join(CorpusHagio, Witness.text_id == CorpusHagio.id)
            .group_by(Manuscript.id)
        )

        if city_name:
            ms_stmt = ms_stmt.where(col(City.name).contains(city_name))
        if dating:
            ms_stmt = ms_stmt.where(col(Witness.dating).contains(dating))

        # Geocode steden enkel als manuscriptlaag aan staat
        city_coords: dict[str, tuple[float, float]] = {}

        def get_coords(name: str):
            if name in city_coords:
                return city_coords[name]
            try:
                from geopy.geocoders import Nominatim
                geo = Nominatim(user_agent="hagiographies-map")
                loc = geo.geocode(name, timeout=5)
                if loc:
                    city_coords[name] = (loc.latitude, loc.longitude)
                    return city_coords[name]
            except Exception:
                pass
            return None

        for row in session.exec(ms_stmt).all():
            coords = get_coords(row.city_name)
            if not coords:
                continue

            def truncate(val, n=4):
                if not val:
                    return "—"
                items = list(dict.fromkeys(v for v in val.split(" · ") if v and v != "None"))
                result = " · ".join(items[:n])
                return result + f" <i>(+{len(items)-n})</i>" if len(items) > n else result

            popup_html = f"""
            <div style="font-family:sans-serif; font-size:13px; min-width:280px; max-width:340px">
                <h4 style="margin:0 0 4px 0">📖 {row.city_name}</h4>
                <i>{row.library_name}</i> — <code>{row.shelfmark}</code>
                <hr style="margin:6px 0">
                <b>Witnesses ({row.witness_count})</b><br>
                <table style="width:100%; font-size:12px; border-collapse:collapse">
                    <tr><td style="color:#888;width:80px">Titels</td>
                        <td>{truncate(row.titles, 3)}</td></tr>
                    <tr><td style="color:#888">BHL</td>
                        <td>{truncate(row.bhl_numbers, 5)}</td></tr>
                    <tr><td style="color:#888">Datering</td>
                        <td>{truncate(row.datings, 3)}</td></tr>
                </table>
            </div>
            """
            folium.CircleMarker(
                location=coords,
                radius=min(5 + row.witness_count * 1.2, 20),
                popup=folium.Popup(popup_html, max_width=360),
                tooltip=f"📖 {row.city_name} — {row.library_name} ({row.witness_count})",
                color="#34495e",
                fill=True,
                fill_color="#95a5a6",
                fill_opacity=0.7,
            ).add_to(ms_cluster)

    folium.LayerControl(collapsed=False).add_to(m)
    return m.get_root().render()


@app.get("/", response_class=HTMLResponse)
def map_view(
    session: Session = Depends(get_session),
    origin: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    dating: Optional[str] = Query(None),
    show_origins: bool = Query(True),
    show_destinations: bool = Query(True),
    show_manuscripts: bool = Query(False),
    show_lines: bool = Query(False),
):
    return build_map(session, origin, city, dating,
                     show_origins, show_destinations, show_manuscripts, show_lines)


@app.get("/api/filters")
def get_filter_options(session: Session = Depends(get_session)):
    origins = session.exec(
        select(Origin.name).where(Origin.name.isnot(None)).distinct()
    ).all()
    cities = session.exec(
        select(City.name).distinct()
    ).all()
    return {
        "origins": sorted(o for o in origins if o),
        "cities": sorted(c for c in cities if c),
    }
