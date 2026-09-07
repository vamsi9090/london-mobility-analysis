# London Transport Infrastructure: OpenStreetMap vs. Government Open Data

### Full analysis report — every number sourced, cross-checked, and every real gap or ambiguity documented rather than smoothed over

This is the third city in this series, after Dublin and Paris. The methodology carries over — cross-referencing OSM against every genuinely open government source, always area-normalizing before comparing, always checking a headline number against a second independently-derived signal — but nothing about London's specific data landscape was assumed in advance. Every source below was located and verified live for this analysis (September 2026).

## 1. Data sources

**OpenStreetMap** — live Overpass API queries against the Greater London administrative relation (OSM relation 175342).

**Government (7 datasets, all fetched live):**

| Dataset | Publisher | Access |
|---|---|---|
| Bus Stops | TfL (GIS Open Data Hub) | ArcGIS FeatureServer |
| Bus Routes | TfL | ArcGIS FeatureServer |
| Taxi Ranks | TfL | ArcGIS FeatureServer |
| Bus Lanes | TfL | ArcGIS FeatureServer |
| Cycle Routes (named corridors) | TfL | ArcGIS FeatureServer |
| Cycling Infrastructure Database (CID) — cycle lane/track segments | TfL | S3 open data (cycling.data.tfl.gov.uk) |
| Greater London Authority (GLA) boundary, London Boroughs | TfL / GLA | ArcGIS FeatureServer |

Unlike Dublin (8 disparate sources, several requiring CRS reprojection) London's government data is unusually well-consolidated: almost everything relevant is published by one organisation (TfL) in one place (its ArcGIS GIS Open Data Hub), already in WGS84. The one genuinely separate source is the CID, TfL's own granular cycling-infrastructure release.

## 2. Methodology

1. **Two independent boundaries checked against each other before anything else.** The government's own GLA administrative boundary (from TfL's ArcGIS hub) and OSM's own Greater London relation boundary were compared directly: intersection-over-union = **0.9999** — for practical purposes the same polygon. This is the up-front version of the boundary check Dublin only ran *after* a clipping bug was found; here it was run first, and the two sources agree closely enough that no correction was needed.
2. **Area normalization is still real, even with matching boundaries.** 5.49% of government bus stops (1,184 of 21,552) and 0.41% of taxi ranks fall outside the GLA polygon — these are TfL-contracted routes/stops that legitimately extend into neighbouring counties (Surrey, Hertfordshire, Essex, Kent). All comparison percentages below exclude these, keeping OSM (queried strictly within the GLA relation) and government data on the same footing.
3. **Every field in every dataset was profiled before writing comparison logic** (`04_column_profile.py`) — this is what surfaced the government bus-route dataset's STATUS field (CURRENT vs. FIRM vs. PROVISIONAL) before it could silently inflate a "routes in OSM" percentage against not-yet-operating routes.
4. **Buffer-tolerant, multi-threshold spatial matching throughout**, not single-distance exact matching — reported at 5/10/15/20/30m so a genuine tagging gap can be told apart from two independently-digitized lines tracing the same real road (the Dublin 2007-vs-2021-survey lesson). Implemented via point-sampling + nearest-neighbour lookup rather than polygon buffer-and-union, because several of these London datasets (up to 75,424 features) are large enough that full geometric union would be impractically slow — the point-sampling approach gives an equivalent answer and scales to this size.

## 3. Bus stops

- Government: 21,552 total, 20,368 inside the GLA boundary.
- OSM: 19,942, all inside the GLA boundary (as expected — Overpass was queried against the same relation).
- **Matching used the shared NAPTAN ATCO code** (present on 93.7% of government stops, 98.7% of OSM stops via the `naptan:AtcoCode` tag) as ground truth — not spatial guessing. 17,964 stops matched by exact code. The remaining stops on each side were matched by nearest-neighbour fallback within 30m, adding 927 more matches.
- **Result: 92.7% of government stops have a matching OSM stop; 94.4% of OSM stops have a matching government stop.** Median distance between matched pairs: 5.0m (code matches), 5.1m (all matches).
- This is consistent with — slightly below — Dublin's 91.9–95.1% bus-stop match rate, a useful cross-city sanity check that the two independent methodologies (ID-based here, purely spatial there) land in the same range.

## 4. Bus routes

- Government: 793 distinct routes with STATUS=CURRENT (of 822 total, once FIRM/PROVISIONAL future routes are excluded).
- OSM: 1,636 relations tagged `route=bus` exist in Greater London, but only 1,362 of those are tagged `network=London Buses` — the rest are Surrey, Hertfordshire, Kent, National Express, Flixbus and other operators' routes passing through the area, not part of the TfL network the government dataset describes. Restricting to `network=London Buses` gives 675 distinct route numbers.
- Leading-zero ref formatting ("035" vs "35") was checked as a possible false mismatch (per Dublin's stray "DB 104" ref-tag lesson) — verified to make no difference here once the network filter is applied.
- **Result: 84.0% of current government routes have a matching OSM relation; 98.7% of OSM's London Buses relations have a matching current government route.**
- The 127 government-only route codes are overwhelmingly non-standard-numeric prefixes (UL, Y, DL, TR, SL — school, night, and route-branch variants), not missing physical routes under their parent number. The 9 OSM-only refs are plausibly stale tagging on discontinued/renumbered routes.
- London's bus-route match rate (84.0%) is substantially higher than Dublin's (50.6%) — a genuine finding, not an artefact of a looser comparison: both used the same "current registered routes vs. matching OSM relation" definition.

## 5. Taxi infrastructure

### 5.1 Taxi ranks

- Government: 728 total, 694 active (`TAXI_STATUS=A`) and inside the GLA boundary.
- OSM: 182 nodes tagged `amenity=taxi`. Inspected individually: 27 of these carry a phone number, website, or opening hours — business-identifying tags typical of a minicab dispatch office, not a marked curbside rank. The remaining 155 are treated as the physical-rank-like subset.
- **Result: only 11.5% of active government taxi ranks have a matching OSM point within 50m; 47.1% of OSM's rank-like nodes have a matching government rank.** Median distance among matches: 10.4m.
- This is a real and striking gap — much larger than the bus-stop gap — and makes sense given the data: London taxi ranks are numerous, small, and curbside-signage-only, without the equivalent of a NAPTAN code or an organized import campaign the way bus stops had. **This is the single largest, clearest OSM-mapping opportunity this analysis found for London.**

### 5.2 Are London's bus lanes and taxi lanes the same thing?

Unlike Dublin (where every taxi-permitted road segment was also bus-permitted, by convention), London's own government data shows this is **not fully true**:

- 84.0% of government bus lane segments explicitly list "Taxi" in their permitted-vehicles field.
- 15.6% are bus-only (or bus + cycle, explicitly excluding taxis).
- Only 13.4% of OSM's designated-lane ways carry any `taxi*` tag at all — meaning OSM under-tags the taxi-permission dimension relative to how often it's actually true in the government data. This is a concrete, actionable OSM tagging gap distinct from the geometry gap below.

## 6. Designated bus/taxi lanes: the geometry gap

- Government: 1,318 lane segments, 286.03 km total length.
- OSM: 3,287 ways carry some designated bus/taxi/psv lane tag (a comprehensive tag list was used here, including per-direction lane-array variants like `bus:lanes:forward` — the same category of tag Dublin's first-pass query missed), 173.00 km total length.
- **At 15m buffer tolerance: 52.2% of the government-documented bus lane network (by length) has a matching OSM-tagged lane; 71.0% of OSM's tagged lane length has a matching government lane.** The coverage curve climbs steadily from 14.4% (5m) to 55.5% (30m) on the government side — a real, if partial, tagging gap, not purely a digitization-alignment artefact (a pure alignment issue would show a much steeper climb-then-plateau).
- **Headline: ~48% of London's official bus lane network (by length) has no matching OSM lane tag within 15m.**

## 7. Cycling infrastructure — classified into three real types on both sides

A naive single "cycling infrastructure" total conflates a physically-segregated track, a painted on-road lane, and a shared footway — three very different things for a cyclist, and Dublin found a naive comparison here can overstate a gap by ~4x. Both sides were classified into the same three types independently: OSM from its own tags (`cycleway=track/lane/shared_lane`, `segregated=`, `foot=designated`, etc.), government from the CID's own boolean flags (`CLT_SEGREG`/`CLT_PARSEG`/`CLT_STEPP` = dedicated track, `CLT_CARR` = on-road, `CLT_SHARED` = shared path).

One real query-scoping bug caught and fixed mid-analysis: the initial OSM cycling query matched on `cycleway`-prefixed tag *key* presence, which pulled in ~21,330 ways whose *value* was `no`/`crossing`/`traffic_island` etc. — explicit absence of infrastructure or junction furniture, not a lane segment. These were excluded before computing any totals (documented in `10_cycling_classification_gap.py`), the value-side counterpart to Dublin's key-side "missed per-direction tags" lesson.

| Type | Government (CID) length | OSM length | Gov length covered by OSM @15m | OSM length covered by Gov @15m |
|---|---|---|---|---|
| Dedicated/segregated track | 319.15 km | 576.17 km | 58.8% | 42.3% |
| On-road painted lane | 632.39 km | 660.59 km | 75.4% | 55.7% |
| Shared-use path | 1,054.89 km | 1,202.89 km | 45.2% | 44.1% |

- **On-road lanes show the closest agreement** (75.4% mutual coverage) — the most standardized, best-mapped category.
- **OSM records notably more "dedicated track" length than the government CID does** (576 vs. 319 km). Read this with a caveat rather than as OSM being "ahead": the OSM classification rule defaults an ambiguous `highway=cycleway` way (no `segregated` or `foot` tag set — true for the majority of London's 32,458 `highway=cycleway` ways) to "dedicated track". Some of that ambiguous length may really be shared-use paths that simply weren't tagged with `segregated`/`foot`, which would move some of the 576 km into the shared-path column instead. This is a classification-scheme sensitivity, not a resolved finding — flagged rather than presented as a clean OSM lead.
- Shared-use paths show the weakest agreement (~45%) in both directions — the least consistently tagged category on both sides, consistent with it being the hardest real-world category to draw a firm boundary on.

## 8. Walking infrastructure

Genuine search (not assumption-by-analogy to Dublin) for a comprehensive open government footway dataset:

| Candidate | Finding |
|---|---|
| OS MasterMap Highways Network – Paths | The accurate, authoritative GB path network — but its data.gov.uk listing has no licence set and no public download link. It is Ordnance Survey's PSGA/premium product, requiring a paid account. |
| OS Detailed Path Network | Genuinely open (OGL) — but explicitly scoped to off-road navigation in National Parks, not urban footways. Does not cover London. |
| OS Open Roads | Free (OGL) with a direct bulk-download API — but explicitly covers vehicle roads only ("motorways to country lanes"); footpaths are not a feature type. |

**Conclusion: as in Dublin, no free, comprehensive, open government footway/pedestrian dataset exists for London. OSM is the only usable source.**

OSM's own walking network, by subtype (Greater London):

| highway= | Count |
|---|---|
| footway | 217,395 |
| path | 15,531 |
| steps | 12,669 |
| pedestrian | 4,641 |
| living_street | 488 |
| **Total** | **250,724 ways** |

This is roughly 4x Dublin's regional (Greater Dublin Area) walking network size, consistent with London's much larger extent and population.

## 9. Recommendations

1. **Map London's taxi ranks in OSM** — the largest, clearest gap found (88.5% of active government ranks have no matching OSM point). A single organized mapping pass against the TfL Taxi Ranks open dataset would close most of this quickly.
2. **Add taxi-permission tags to designated lanes in OSM** — only 13.4% of OSM's lane ways carry any `taxi*` tag, versus 84.0% of government-documented bus lanes that actually permit taxis. This is a tagging gap, not a geometry gap, and is cheap to fix once the government dataset is used as a reference.
3. **Close the ~48% bus-lane geometry gap** (by length, at 15m tolerance) using the government Bus_Lanes dataset as an import/verification source, the same opportunity Dublin found (83% gap) though less severe here.
4. **Re-run the OSM cycling "dedicated track" classification with a stricter rule** requiring an explicit `segregated=yes` (rather than defaulting ambiguous `highway=cycleway` ways to dedicated) before treating the 576 vs. 319 km gap as a real OSM-ahead-of-government finding.
5. **UL/Y/DL/TR/SL-prefixed bus routes** (127 of them) are the most likely near-term OSM route-relation mapping gap; check a sample against TfL's live route data before assuming the physical road segments are unmapped rather than just the route relation itself.

## 10. Cross-city comparison so far

| Metric | Dublin | Paris | London |
|---|---|---|---|
| Bus stop match rate (gov) | 91.9–95.1% | — | 92.7% |
| Bus route match rate (gov, current) | 50.6% | — | 84.0% |
| Bus lane gap (gov length not in OSM) | 83.2% | — | ~48% (15m tolerance) |
| Comprehensive open gov footway dataset? | No | — | No |
| Taxi lanes = bus lanes by convention? | Yes (fully) | — | No (84% overlap, not full) |

(Paris figures not restated here since this report covers London only; see `paris-mobility-analysis` for that comparison.)
