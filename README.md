# Maritime Safety Evidence Observatory

An interactive portfolio prototype that turns public UK Marine Accident Investigation Branch (MAIB) occurrence data into an evidence-aware analytical dashboard.

**[Open the live dashboard](https://maritime-safety-evidence-observatory.oakenwhale32768.chatgpt.site/)**

The published snapshot contains 9,063 occurrence records, 9,830 linked vessel records and 3,040 affected-person records covering 2020–2026. The latest year is explicitly marked as partial.

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
- an automatically assembled, print-ready evidence brief;
- deterministic five-fold model validation with ROC AUC, average precision, calibration, Brier score, sensitivity, precision and specificity;
- release-blocking relationship and coordinate checks plus source-file SHA-256 fingerprints.

## How the analysis works

### 1. Build a relational analytical dataset

The three source tables are joined through `Occurrence_Id` while preserving their different units of analysis:

| Analytical level | Source grain | Main use |
| --- | --- | --- |
| Occurrence | One reported occurrence | Trends, geography, event mix and occurrence severity |
| Vessel | One vessel linked to an occurrence | Collision pairings, vessel age, tonnage and damage outcomes |
| Affected person | One person linked to an occurrence | Injury outcomes, person roles, duty status and event-to-outcome flows |

The build checks duplicate occurrence IDs, orphaned vessel/person records, coordinate bounds and required outcome classes. Unknown values are retained as explicit categories or indicators rather than silently converted to normal conditions. Source-file SHA-256 fingerprints make each published snapshot traceable.

### 2. Define the descriptive measures

- Occurrence counts are grouped by year, event, vessel category, severity and location.
- People injured are records with `Physical_Condition_L1 = Injured`.
- Deaths include confirmed deaths and people recorded as missing with death presumed. Vessel-level casualty totals are fallback-only when an occurrence has no affected-person rows, preventing double counting.
- Serious shares are calculated within reported records and accompanied by Wilson 95% confidence intervals where appropriate.
- Collision cells count unique collision occurrences containing each vessel-category pairing. Pairings are deduplicated within an occurrence and displayed once in the matrix.
- Vessel age is occurrence year minus year built; unusable tonnage remains `Unknown / zero`.

### 3. Fit three multivariable logistic models

| Model | Binary outcome | Main explanatory variables |
| --- | --- | --- |
| Occurrence severity | Serious or very serious classification | Event, vessel categories, environmental conditions, multi-vessel status and year |
| Person consequence | Serious injury, confirmed death or presumed death | Age, gender, person type, duty status, vessel category and event |
| Vessel damage | Material damage or vessel loss | Vessel age, log10 gross tonnage, vessel category, event, multi-vessel status and year |

Results are reported as adjusted odds ratios with 95% confidence intervals. Person and vessel models use occurrence-clustered standard errors because several people or vessels can belong to the same occurrence.

### 4. Validate out of sample

All models use deterministic five-fold cross-validation. Person and vessel folds are grouped by `Occurrence_Id`, preventing related rows from the same occurrence appearing in both training and validation data. The dashboard reports out-of-fold ROC AUC, average precision, Brier score, calibration, sensitivity, precision, specificity and a confusion matrix at a 0.50 threshold.

This matters because ROC AUC alone can look acceptable for an imbalanced outcome even when sensitivity at a fixed threshold is low.

### 5. Keep the interpretation within the data

The analysis answers which characteristics are associated with outcomes **among published MAIB records**. It does not estimate fleet-wide accident probability or prove causation. Exposure-adjusted risk would require compatible denominators such as voyages, vessel-hours, distance travelled or vessel traffic for the same geography, period and vessel classification.

See [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the complete definitions and statistical boundaries.

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

## Roadmap

- point-in-time Copernicus wave/current matching for individual occurrences;
- port-arrival denominators for port-area comparisons;
- page-level extraction from published investigation reports;
- citation validation and retrieval evaluation;
- versioned data refresh and reproducibility report.
