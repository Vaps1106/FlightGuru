"""Trim the OurAirports dataset down to the airports FlightGuru actually searches.

OurAirports ships ~86,000 rows, most of them heliports, seaplane bases and private
strips with no commercial service. We keep only airports that have BOTH a real
IATA code and scheduled service, which is the set Google Flights can price.

Deliberately NOT filtered by airport size. Small fields are exactly where the
low-cost carriers operate -- Tweed New Haven (HVN) is Avelo's base, Portsmouth
(PSM) is Breeze -- and a large/medium-only cut would silently drop the cheap
fares this whole feature exists to find.

Run:  python scripts/build_airports.py <source_csv> <output_csv>

Source: https://davidmegginson.github.io/ourairports-data/airports.csv (public domain)
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Columns we keep. Everything else (elevation, wikipedia links, GPS codes) is
# dead weight for a price search.
FIELDS = ["iata", "name", "city", "country", "region", "lat", "lon", "size"]

# OurAirports "type" -> a short label we can show the user. Anything not listed
# here (heliports, seaplane bases, balloonports, closed fields) is dropped
# outright: several carry IATA codes and are flagged as having scheduled
# service, so without this filter a search near JFK fills up with Manhattan
# heliports and a seaplane dock and never reaches Newark.
SIZE_LABELS = {
    "large_airport": "large",
    "medium_airport": "medium",
    "small_airport": "small",
}


def build(source: Path, output: Path) -> int:
    """Write the trimmed CSV. Returns the number of airports kept."""
    kept: list[dict[str, str]] = []
    seen: set[str] = set()

    with source.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            iata = (row.get("iata_code") or "").strip().upper()
            # No IATA code means Google Flights cannot be asked about it.
            if len(iata) != 3 or not iata.isalpha():
                continue
            if (row.get("scheduled_service") or "").strip().lower() != "yes":
                continue
            size = SIZE_LABELS.get((row.get("type") or "").strip())
            if size is None:  # heliport, seaplane base, closed field, etc.
                continue
            # A handful of IATA codes appear twice in the source; first wins.
            if iata in seen:
                continue

            lat = (row.get("latitude_deg") or "").strip()
            lon = (row.get("longitude_deg") or "").strip()
            if not lat or not lon:
                continue

            seen.add(iata)
            kept.append(
                {
                    "iata": iata,
                    "name": (row.get("name") or "").strip(),
                    "city": (row.get("municipality") or "").strip(),
                    "country": (row.get("iso_country") or "").strip(),
                    "region": (row.get("iso_region") or "").strip(),
                    "lat": lat,
                    "lon": lon,
                    "size": size,
                }
            )

    kept.sort(key=lambda a: a["iata"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(kept)

    return len(kept)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1
    count = build(Path(argv[0]), Path(argv[1]))
    print(f"Wrote {count} airports to {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
