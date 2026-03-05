# Artifact Citation Verification

## Summary

**Zero genuine third-party artifact citations** were found across 782 artifact DOIs
(Zenodo & Figshare) from 2,576 artifacts in our dataset (March 2026).

OpenAlex reported 14 artifacts with a total of 43 citing DOIs. We verified every
citing DOI and found:

| Verdict | Count | Description |
|---------|------:|-------------|
| FALSE_POSITIVE | 36 | Citing paper's bibliography references the *paper* DOI, not the artifact DOI |
| SELF_CITATION | 6 | The paper cites its own artifact (overlapping authors) |
| UNKNOWN | 1 | arXiv preprint whose references could not be resolved via Crossref |
| **GENUINE** | **0** | — |

## Why OpenAlex Citations Are Unreliable for Artifact DOIs

When an artifact on Zenodo inherits the same title as the published paper (which
is the default behavior), OpenAlex may conflate the two records. A paper that
cites the *paper* DOI gets attributed as also citing the *artifact* DOI, because
OpenAlex treats them as the same work based on title matching.

This means **reported citation counts for artifact DOIs are inflated** by citations
to the corresponding paper — and, in practice, this accounts for the vast majority
of reported citations.

## Verification Methodology

### Step 1: Crossref Reference List Check

For each citing DOI, we query the Crossref API to retrieve the publisher-submitted
reference list (`message.reference[]`). We then check whether any reference in
that list contains the artifact DOI (matching `10.5281/zenodo.*` or
`10.6084/m9.figshare.*` prefixes).

- If the artifact DOI is found in the references → passes to Step 2
- If not → **FALSE_POSITIVE** (the paper cited the paper DOI, not the artifact)

### Step 2: Self-Citation Detection

For citing DOIs that pass Step 1, we compare author lists between the cited
artifact (from the Zenodo API) and the citing paper (from the Crossref API).
Surnames are extracted and normalized (lowercased, ≥3 characters).

- If ≥2 surnames overlap → **SELF_CITATION**
- Otherwise → **GENUINE**

### Step 3: Manual Verification

One citing DOI (`10.1007/978-3-031-61486-6_4` citing `10.5281/zenodo.6353717`)
passed both automated checks but was manually verified to be a mistake: the
citing paper intended to reference the Narwhal paper, not the Zenodo artifact.
The Zenodo DOI appears in the bibliography by error.

## Scripts

### `src/generators/verify_artifact_citations.py`

The main verification script. Reads `artifact_citations.json` (output from the
citation collection pipeline) and verifies each citing DOI against Crossref
reference lists.

**Usage:**
```bash
HTTP_PROXY=http://your-proxy:port HTTPS_PROXY=http://your-proxy:port \
  python3 -m src.generators.verify_artifact_citations \
    --data_dir ../researchartifacts.github.io \
    --output citation_verification.json
```

**Outputs:**
- `citation_verification.json` — Per-DOI verdict (GENUINE, FALSE_POSITIVE, SELF_CITATION, UNKNOWN) with reasoning
- `citation_verification_genuine.txt` — List of genuine third-party citations (currently empty)
- `citation_verification_false_positives.txt` — List of false positives

### `src/generators/generate_artifact_citations.py`

The citation collection pipeline. **Disabled by default** (requires `--enable-citations` flag).
Queries OpenAlex for citation counts on artifact DOIs.

**Usage:**
```bash
python3 -m src.generators.generate_artifact_citations \
  --data_dir ../researchartifacts.github.io \
  --enable-citations
```

### `src/generators/export_artifact_citations.py`

Export artifact DOI → citing DOI mappings.

## Output Files

| File | Description |
|------|-------------|
| `citation_verification.json` | Per-DOI results: verdict, reason, artifact_doi, citing_doi, shared_authors |
| `citation_verification_genuine.txt` | Empty (no genuine citations) |
| `citation_verification_false_positives.txt` | 35 artifact→citing DOI pairs that are false positives |
| `artifact_citing_dois.txt` | 14 artifacts with their 43 citing DOIs (raw, pre-verification) |

## Implications

1. **Citation counts should not be used in rankings** until indexes can distinguish artifact vs. paper DOIs.
2. **Authors should give artifacts distinct titles** (not identical to the paper title) to enable proper DOI disambiguation.
3. **Zenodo/Figshare should expose relationship metadata** (e.g., "isSupplementTo") that indexes can use to separate artifact from paper citations.
4. **Future work** should revisit this analysis periodically to check whether the situation improves.
