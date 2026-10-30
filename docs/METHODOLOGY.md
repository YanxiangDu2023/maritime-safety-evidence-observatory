# Methodology and metric definitions

## Units of analysis

- **Occurrence:** one row in the MAIB occurrence export.
- **Vessel:** one vessel linked to an occurrence through `Occurrence_Id`.
- **Affected person:** one person record linked to an occurrence and, when available, a vessel.

Multi-vessel occurrences are retained in vessel-level analyses. They may appear in more than one vessel-category row in the severity matrix.

## Human-consequence metrics

- **People injured:** `Physical_Condition_L1 = Injured`.
- **Deaths / presumed deaths:** `Physical_Condition_L1` is `Death (confirmed)` or `Missing (death presumed)`.
- Vessel-level totals are used only for an occurrence with no affected-person rows. This avoids double counting.

### Person injury-severity model

The person-level binary outcome combines `Physical_Condition_L2 = Serious injury`,
confirmed deaths and persons recorded as missing with death presumed. Minor injury,
no injury and unavailable injury severity form the reference outcome. Predictors
include age, gender, person type, duty status, vessel category and occurrence event.
Missing age, gender and
duty status are represented explicitly. Wald intervals use an occurrence-clustered
sandwich covariance matrix because multiple people may belong to one occurrence.
Five-fold validation is grouped by `Occurrence_Id`, so one occurrence cannot
appear in both the training and test portions of a fold.

## Severity model

The binary outcome is `Occurrence_Severity` classified as `Serious` or `Very Serious`; the reference outcome combines `Marine incident` and `Less serious`.

The multivariable logistic regression reports adjusted odds ratios and Wald 95% confidence intervals. Environmental unknown values receive explicit indicator variables. Results are validated with deterministic stratified five-fold cross-validation. The dashboard reports out-of-fold ROC AUC, Brier score, a confusion matrix at a 0.50 threshold, and decile calibration.

The model is conditional on an occurrence entering the MAIB dataset. It does not estimate accident probability, population risk, or causal effects.

## External geographic context

The context map displays MAIB occurrence locations over official EMODnet Web Map Service layers. Vessel density is an annual average of AIS-derived vessel hours per square kilometre per month. The interface uses the overlapping 2020–2024 period and preserves EMODnet vessel-type categories. The 2024 layer carries the provider's warning about reduced satellite coverage from June. Bathymetry is displayed as mean seabed depth from the current EMODnet source grid.

Port comparisons use the Department for Transport PORT0499 dataset. Source values are reported in thousands of tonnes and are converted to tonnes before the browser-ready summary is generated. Freight tonnage is operational context and is not treated as a direct denominator for every occurrence type.

These layers remain contextual rather than a calculated risk surface. A valid exposure-adjusted rate requires compatible geography, time period and vessel classification. Copernicus wave reanalysis is documented as a point-in-time enrichment source; it should be matched to each occurrence's coordinates and timestamp before entering descriptive or regression analysis.

## Vessel profiles

- Vessel age is calculated as occurrence year minus year built.
- Zero or unusable tonnage is shown as `Unknown / zero` rather than treated as a measured zero.
- Damage shares are conditional on vessels represented in reported occurrences.

### Collision pairing matrix

The collision matrix is limited to occurrences whose main event is `Collision`
and which contain at least two linked vessel records. A cell counts unique
occurrences containing the displayed vessel-category pairing. Pairings are
deduplicated within an occurrence; an occurrence involving more than two vessels
may still contribute to more than one distinct pairing. Serious shares use Wilson
95% intervals.

### Vessel damage model

The vessel-level outcome is material damage or vessel loss; no damage and minor
damage form the reference. Vessel age and log10 gross tonnage are continuous,
with explicit unknown indicators. Vessel category, event type, multi-vessel status
and calendar year are adjusted simultaneously. Standard errors and five-fold
validation are grouped by `Occurrence_Id` to account for multiple vessels linked
to the same occurrence. The model is conditional on a vessel appearing in the
published occurrence data and is not a fleet-wide damage probability.

## Partial year

The latest year is incomplete and is visually separated in the time-series chart. It should not be compared directly with complete years.

## Reproducibility and release checks

The build records SHA-256 fingerprints for each raw source file. It fails before publication if occurrence IDs are duplicated, linked rows are orphaned, serious outcomes are absent, or coordinates violate valid geographic bounds. Unit tests protect the person-outcome classifications and expected source snapshot counts.

Run:

```bash
python3 scripts/refresh_data.py
python3 scripts/build_data.py
python3 -m unittest discover -s tests -v
node --check dist/app.js
```
