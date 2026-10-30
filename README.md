# Maritime Safety Evidence Observatory

An interactive portfolio prototype that turns public UK Marine Accident Investigation Branch (MAIB) occurrence data into an evidence-aware analytical dashboard.

## What it demonstrates

- relational integration of occurrence, vessel and affected-person records;
- automatic completeness and relationship-integrity checks;
- interactive temporal, geographic and categorical analysis;
- a filter-aware geographic context view combining MAIB occurrence locations with EMODnet vessel-density and bathymetry WMS layers;
- an official DfT port-freight comparison for the overlapping 2020–2024 period;
- a multivariable logistic model of serious/very serious classification with adjusted odds ratios and 95% confidence intervals;
- person-level event-to-outcome flows and vessel-level damage profiles by age and gross tonnage;
- occurrence-clustered person injury-severity and vessel material-damage models;
- a collision pairing matrix retaining the vessel combinations within multi-vessel occurrences;
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

Refresh the official DfT port-freight context and rebuild its browser summary:

```bash
python3 scripts/refresh_context_data.py
```

EMODnet vessel-density and bathymetry layers are requested through their official WMS endpoints at display time; they are not copied into this repository.

Validate the analytical artifact before publication:

```bash
python3 -m unittest discover -s tests -v
node --check dist/app.js
```

## Scheduled refresh

The production Site is checked on the first Monday of each month. The safe
refresh entry point downloads the official sources, rebuilds the analytical
artifacts and runs all release checks:

```bash
python3 scripts/automated_refresh.py
```

Its JSON result sets `publish_required` to `true` only when analytical content
has changed. A build timestamp alone does not trigger publication. If download,
schema validation, modelling or tests fail, the previous browser artifacts are
restored and the live Site must remain on its last successful version.

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

- point-in-time Copernicus wave/current matching for individual occurrences;
- port-arrival denominators for port-area comparisons;
- page-level extraction from published investigation reports;
- citation validation and retrieval evaluation;
- versioned data refresh and reproducibility report.
