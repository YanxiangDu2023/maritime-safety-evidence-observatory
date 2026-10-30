# Maritime Safety Evidence Observatory

An interactive portfolio prototype that turns public UK Marine Accident Investigation Branch (MAIB) occurrence data into an evidence-aware analytical dashboard.

## What it demonstrates

- relational integration of occurrence, vessel and affected-person records;
- automatic completeness and relationship-integrity checks;
- interactive temporal, geographic and categorical analysis;
- a multivariable logistic model of serious/very serious classification with adjusted odds ratios and 95% confidence intervals;
- person-level event-to-outcome flows and vessel-level damage profiles by age and gross tonnage;
- explicit separation of reported occurrence counts from exposure-adjusted risk;
- source-linked investigation evidence;
- an automatically assembled, print-ready evidence brief.
- deterministic five-fold model validation, calibration and Brier-score reporting;
- release-blocking relationship and coordinate checks plus source-file SHA-256 fingerprints.

## Data source

The project uses the three public CSV exports from the [MAIB Data Portal](https://maps.dft.gov.uk/maib-data-portal/web-pages/download_files_section.html). Raw data is not committed to the repository. The browser-ready analytical file is generated locally with `scripts/build_data.py`.

## Build the analytical dataset

Download the MAIB files to `data/raw/` as:

- `occurrences.csv`
- `vessels.csv`
- `affected_persons.csv`

Or refresh all three files from the official MAIB download endpoints:

```bash
python3 scripts/refresh_data.py
```

Then run:

```bash
python3 scripts/build_data.py
```

Validate the analytical artifact before publication:

```bash
python3 -m unittest discover -s tests -v
node --check dist/app.js
```

## Run locally

Serve the project root with a static HTTP server and open `dist/`:

```bash
python3 -m http.server 8000 --directory dist
```

## Methodological boundary

The dashboard describes reported occurrences. It does not estimate the probability that a vessel will experience an accident. Comparisons of raw counts by vessel category require an exposure denominator such as fleet size, voyages, distance travelled or operating hours before they can be interpreted as risk rates.

The severity model is conditional on an occurrence appearing in the MAIB dataset. Its adjusted odds ratios describe associations with the published severity classification; they are not causal effects and should not be interpreted as accident-risk estimates.

See [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for metric definitions, model validation and reproducibility controls.

## Roadmap

- page-level extraction from published investigation reports;
- citation validation and retrieval evaluation;
- exposure-denominator integration;
- regression analysis of severity conditional on a reported occurrence;
- versioned data refresh and reproducibility report.
