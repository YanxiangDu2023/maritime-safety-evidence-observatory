# Maritime Safety Evidence Observatory

An interactive portfolio prototype that turns public UK Marine Accident Investigation Branch (MAIB) occurrence data into an evidence-aware analytical dashboard.

## What it demonstrates

- relational integration of occurrence, vessel and affected-person records;
- automatic completeness and relationship-integrity checks;
- interactive temporal, geographic and categorical analysis;
- explicit separation of reported occurrence counts from exposure-adjusted risk;
- source-linked investigation evidence;
- an automatically assembled, print-ready evidence brief.

## Data source

The project uses the three public CSV exports from the [MAIB Data Portal](https://maps.dft.gov.uk/maib-data-portal/web-pages/download_files_section.html). Raw data is not committed to the repository. The browser-ready analytical file is generated locally with `scripts/build_data.py`.

## Build the analytical dataset

Download the MAIB files to `data/raw/` as:

- `occurrences.csv`
- `vessels.csv`
- `affected_persons.csv`

Then run:

```bash
python3 scripts/build_data.py
```

## Run locally

Serve the project root with a static HTTP server and open `dist/`:

```bash
python3 -m http.server 8000 --directory dist
```

## Methodological boundary

The dashboard describes reported occurrences. It does not estimate the probability that a vessel will experience an accident. Comparisons of raw counts by vessel category require an exposure denominator such as fleet size, voyages, distance travelled or operating hours before they can be interpreted as risk rates.

## Roadmap

- page-level extraction from published investigation reports;
- citation validation and retrieval evaluation;
- exposure-denominator integration;
- regression analysis of severity conditional on a reported occurrence;
- versioned data refresh and reproducibility report.
