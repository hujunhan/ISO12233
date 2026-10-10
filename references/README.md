# Local references

Download the original Westin references for measurement and validation:

```bash
curl -fL https://www.graphics.cornell.edu/~westin/misc/ISO_12233-reschart.svg -o references/ISO_12233-reschart.svg
curl -fL https://www.graphics.cornell.edu/~westin/misc/ISO_12233-reschart.pdf -o references/ISO_12233-reschart.pdf
shasum -a 256 references/ISO_12233-reschart.svg references/ISO_12233-reschart.pdf
```

The exact reference fingerprints used for this reconstruction are:

| File | SHA-256 |
|---|---|
| SVG | `0ec61f2f985fef344053e1d8ca7e80743cf9980fb026a8d59063be34dec59e1b` |
| PDF | `a1fd4cc763150eca220736cf8eaae47edaf08ff895e4674e2890b866c2027ffe` |

Both are Westin/Cornell copyrighted artwork, not CC0. The originals contain
embedded proprietary font subsets. They remain untracked local references;
the generator uses the separately licensed Liberation Sans font instead.
If fingerprints differ, investigate the source revision before re-measuring.
The author disclaims ISO compliance; preserve that distinction in downstream use.

## Modern charts

Public source URLs, local filenames, SHA-256 fingerprints, coverage and approximate
preview measurements are recorded in [data/modern_references.json](../data/modern_references.json).
See [docs/modern-charts.md](../docs/modern-charts.md) for the selected parameters and
unverified details. Downloaded PDFs and preview images remain ignored local references;
public access does not imply permission to redistribute their originals.
