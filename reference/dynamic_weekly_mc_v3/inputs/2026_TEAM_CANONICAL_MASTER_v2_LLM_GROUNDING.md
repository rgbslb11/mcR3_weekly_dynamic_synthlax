# 2026 FBS Team Canonical Master v2 — LLM Grounding File

> **Purpose:** Canonical grounding reference for the 2026 synthetic college-football universe. Load this file into the model/context whenever team identity, membership, schedule identifiers, conference alignment, Board I-H fields, or related team-master attributes must be resolved.

## Authority and Grounding Contract

- **This file is authoritative for the synthetic universe represented by the supplied canonical master.** When this file conflicts with general model knowledge or real-world NCAA knowledge, use this file.
- The universe contains **134 canonical schedule entities**: **121 governed FBS members** plus **13 schedule-only opponents labeled FCS**.
- **Do not add, remove, promote, demote, rename, merge, or reclassify a team from outside knowledge.** In particular, do not change a `SCHEDULE_ONLY_FCS` record merely because real-world knowledge suggests a different classification.
- Treat `schedule_id` as the unique schedule-facing identifier. There are exactly **134 unique `schedule_id` values**.
- For `SCHEDULE_ONLY_FCS` rows, `master_team_id` and `name_id` are intentionally blank unless a governed source provides them. **Never invent either identifier.**
- For schedule-only FCS rows, `2026_conference` is populated only when the governed FCS reference explicitly supports it; otherwise it remains blank. `schedule_conference_label` remains `FCS`.
- Blank source fields are represented in this Markdown as `<blank>`. **Blank means unset/unsupported in the source—not permission to infer a value.**
- Board, stadium, HFA, and detailed team-master fields that are blank for schedule-only FCS rows must remain blank unless a later governed artifact supersedes this file.
- If a requested team or identifier is not present here, return **BLOCKED — NOT IN 2026 CANONICAL TEAM MASTER** rather than fabricating a match.
- If two user references appear ambiguous, resolve using exact `schedule_id`, then governed IDs (`master_team_id` / `name_id` where present), then exact `team_name`, `abbreviated_name`, and `aka_name`. Do not use outside aliases to override a canonical record.

## Source Metadata

- Artifact: `2026_TEAM_CANONICAL_MASTER_v2.csv`
- Status: `CANONICAL CANDIDATE — FBS MASTER PLUS SCHEDULE-ONLY FCS OPPONENTS`
- Created date: `2026-07-23`
- Supersedes: `2026_TEAM_CANONICAL_MASTER_v1.csv`
- Source CSV SHA-256: `2ff50af98b732721189662db4e21b2285136c3561fce2200ae438daa1296cb3a`
- Total rows: **134**
- FBS rows: **121**
- Schedule-only FCS rows: **13**
- Unique schedule IDs: **134**

### Governed upstream sources named by the manifest

- `base_master`: `2026_TEAM_CANONICAL_MASTER_v1.csv`
- `schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `registry`: `Canonical Season Registry.xlsx`
- `fcs_reference`: `Project FCS: CFB26 (Google Drive)`

## Supplied Data-Dictionary Policies

- `schedule_id` and `abbreviated_name` for the 13 schedule-only FCS records come directly from schedule v5.
- `team_name` and `aka_name` for those records are populated only from the Canonical Season Registry or `Project FCS: CFB26`.
- `master_team_id` and `name_id` are blank for all 13 schedule-only FCS rows because no governed values were surfaced.
- `2026_division` is `FCS` for those 13 records because schedule v5 labels them as FCS.
- `schedule_conference_label` is `FCS` for those records.
- `2026_conference` is populated only where the FCS reference explicitly provides one; otherwise it is blank.
- Board, stadium, HFA, and detailed team-master fields remain blank for those FCS records.
- `entity_scope` is either `FBS_MEMBER` or `SCHEDULE_ONLY_FCS`.
- No FCS numeric IDs were invented.

## Canonical Schema

The source CSV contains the following **35 fields, in source order**. Fields not separately defined by the supplied data dictionary must be preserved literally; this grounding file does not invent new semantics for them.

1. `master_team_id`
2. `name_id`
3. `team_name`
4. `abbreviated_name`
5. `aka_name`
6. `schedule_id`
7. `2026_conference`
8. `2026_division`
9. `2026_conference_division`
10. `power_conference_flag`
11. `g5_flag`
12. `independent_flag`
13. `stadium`
14. `home_field_advantage_modifier`
15. `regular_season_games`
16. `home_listed_games`
17. `away_listed_games`
18. `neutral_site_games`
19. `conference_games`
20. `board_rank_H`
21. `board_committee_H`
22. `board_power_H`
23. `championship_eligible`
24. `identity_validation_status`
25. `schedule_validation_status`
26. `board_validation_status`
27. `source_team_master`
28. `source_schedule`
29. `source_board`
30. `source_registry`
31. `provenance_codes`
32. `notes`
33. `entity_scope`
34. `schedule_conference_label`
35. `source_fcs_reference`

## Schedule-Only FCS Exception Set

These 13 records are deliberately **not members of the 121-team FBS population** in this synthetic universe. Their source rows are preserved exactly below.

| schedule_id | team_name | supported 2026_conference | regular_season_games | master_team_id | name_id |
|---|---|---|---:|---|---|
| `ARST` | Arkansas State | `<blank>` | 1 | `<blank>` | `<blank>` |
| `CHAR` | Charlotte | `<blank>` | 1 | `<blank>` | `<blank>` |
| `CP` | Cal Poly | `Big Sky` | 1 | `<blank>` | `<blank>` |
| `DUQ` | Duquesne | `NEC` | 1 | `<blank>` | `<blank>` |
| `EMU` | Eastern Michigan | `<blank>` | 1 | `<blank>` | `<blank>` |
| `IDHO` | Idaho | `Big Sky` | 2 | `<blank>` | `<blank>` |
| `SAC` | Sacramento State | `Big Sky` | 2 | `<blank>` | `<blank>` |
| `SUU` | Southern Utah | `UAC` | 1 | `<blank>` | `<blank>` |
| `TOL` | Toledo | `<blank>` | 1 | `<blank>` | `<blank>` |
| `ULL` | Louisiana (UL Lafayette) | `<blank>` | 1 | `<blank>` | `<blank>` |
| `ULM` | Louisiana-Monroe | `<blank>` | 1 | `<blank>` | `<blank>` |
| `WKU` | Western Kentucky | `<blank>` | 1 | `<blank>` | `<blank>` |
| `WMU` | Western Michigan | `<blank>` | 1 | `<blank>` | `<blank>` |

## Canonical Team Index — All 134 Entities

Use this index for fast identity resolution. Full source records follow in the next section.

| # | schedule_id | team_name | abbreviated_name | entity_scope | 2026_division | 2026_conference | master_team_id | name_id |
|---:|---|---|---|---|---|---|---|---|
| 1 | `ALA` | Alabama | `ALA` | `FBS_MEMBER` | `FBS` | `SEC` | `1` | `team-001-alabama` |
| 2 | `ARK` | Arkansas | `ARK` | `FBS_MEMBER` | `FBS` | `SEC` | `2` | `team-002-arkansas` |
| 3 | `AUB` | Auburn | `AUB` | `FBS_MEMBER` | `FBS` | `SEC` | `3` | `team-003-auburn` |
| 4 | `FLA` | Florida | `FLA` | `FBS_MEMBER` | `FBS` | `SEC` | `4` | `team-004-florida` |
| 5 | `UGA` | Georgia | `UGA` | `FBS_MEMBER` | `FBS` | `SEC` | `5` | `team-005-georgia` |
| 6 | `UK` | Kentucky | `UK` | `FBS_MEMBER` | `FBS` | `SEC` | `6` | `team-006-kentucky` |
| 7 | `LSU` | LSU | `LSU` | `FBS_MEMBER` | `FBS` | `SEC` | `7` | `team-007-lsu` |
| 8 | `MSST` | Mississippi State | `MSST` | `FBS_MEMBER` | `FBS` | `SEC` | `8` | `team-008-mississippi-state` |
| 9 | `MIZ` | Missouri | `MIZ` | `FBS_MEMBER` | `FBS` | `SEC` | `9` | `team-009-missouri` |
| 10 | `OU` | Oklahoma | `OU` | `FBS_MEMBER` | `FBS` | `SEC` | `10` | `team-010-oklahoma` |
| 11 | `MISS` | Ole Miss | `MISS` | `FBS_MEMBER` | `FBS` | `SEC` | `11` | `team-011-ole-miss` |
| 12 | `SC` | South Carolina | `SC` | `FBS_MEMBER` | `FBS` | `SEC` | `12` | `team-012-south-carolina` |
| 13 | `TENN` | Tennessee | `TENN` | `FBS_MEMBER` | `FBS` | `SEC` | `13` | `team-013-tennessee` |
| 14 | `TEX` | Texas | `TEX` | `FBS_MEMBER` | `FBS` | `SEC` | `14` | `team-014-texas` |
| 15 | `TA&M` | Texas A&M | `TA&M` | `FBS_MEMBER` | `FBS` | `SEC` | `15` | `team-015-texas-a-and-m` |
| 16 | `VAN` | Vanderbilt | `VAN` | `FBS_MEMBER` | `FBS` | `SEC` | `16` | `team-016-vanderbilt` |
| 17 | `ILL` | Illinois | `ILL` | `FBS_MEMBER` | `FBS` | `Big Ten` | `17` | `team-017-illinois` |
| 18 | `IU` | Indiana | `IU` | `FBS_MEMBER` | `FBS` | `Big Ten` | `18` | `team-018-indiana` |
| 19 | `IOWA` | Iowa | `IOWA` | `FBS_MEMBER` | `FBS` | `Big Ten` | `19` | `team-019-iowa` |
| 20 | `MD` | Maryland | `MD` | `FBS_MEMBER` | `FBS` | `Big Ten` | `20` | `team-020-maryland` |
| 21 | `MICH` | Michigan | `MICH` | `FBS_MEMBER` | `FBS` | `Big Ten` | `21` | `team-021-michigan` |
| 22 | `MSU` | Michigan State | `MSU` | `FBS_MEMBER` | `FBS` | `Big Ten` | `22` | `team-022-michigan-state` |
| 23 | `MINN` | Minnesota | `MINN` | `FBS_MEMBER` | `FBS` | `Big Ten` | `23` | `team-023-minnesota` |
| 24 | `NEB` | Nebraska | `NEB` | `FBS_MEMBER` | `FBS` | `Big Ten` | `24` | `team-024-nebraska` |
| 25 | `NU` | Northwestern | `NU` | `FBS_MEMBER` | `FBS` | `Big Ten` | `25` | `team-025-northwestern` |
| 26 | `OSU` | Ohio State | `OSU` | `FBS_MEMBER` | `FBS` | `Big Ten` | `26` | `team-026-ohio-state` |
| 27 | `ORE` | Oregon | `ORE` | `FBS_MEMBER` | `FBS` | `Big Ten` | `27` | `team-027-oregon` |
| 28 | `PSU` | Penn State | `PSU` | `FBS_MEMBER` | `FBS` | `Big Ten` | `28` | `team-028-penn-state` |
| 29 | `PUR` | Purdue | `PUR` | `FBS_MEMBER` | `FBS` | `Big Ten` | `29` | `team-029-purdue` |
| 30 | `RUTG` | Rutgers | `RUTG` | `FBS_MEMBER` | `FBS` | `Big Ten` | `30` | `team-030-rutgers` |
| 31 | `UCLA` | UCLA | `UCLA` | `FBS_MEMBER` | `FBS` | `Big Ten` | `31` | `team-031-ucla` |
| 32 | `USC` | USC | `USC` | `FBS_MEMBER` | `FBS` | `Big Ten` | `32` | `team-032-usc` |
| 33 | `WASH` | Washington | `WASH` | `FBS_MEMBER` | `FBS` | `Big Ten` | `33` | `team-033-washington` |
| 34 | `WIS` | Wisconsin | `WIS` | `FBS_MEMBER` | `FBS` | `Big Ten` | `34` | `team-034-wisconsin` |
| 35 | `ARIZ` | Arizona | `ARIZ` | `FBS_MEMBER` | `FBS` | `Big 12` | `35` | `team-035-arizona` |
| 36 | `ASU` | Arizona State | `ASU` | `FBS_MEMBER` | `FBS` | `Big 12` | `36` | `team-036-arizona-state` |
| 37 | `BYU` | BYU | `BYU` | `FBS_MEMBER` | `FBS` | `Big 12` | `37` | `team-037-byu` |
| 38 | `BAY` | Baylor | `BAY` | `FBS_MEMBER` | `FBS` | `Big 12` | `38` | `team-038-baylor` |
| 39 | `CIN` | Cincinnati | `CIN` | `FBS_MEMBER` | `FBS` | `Big 12` | `39` | `team-039-cincinnati` |
| 40 | `COLO` | Colorado | `COLO` | `FBS_MEMBER` | `FBS` | `Big 12` | `40` | `team-040-colorado` |
| 41 | `HOU` | Houston | `HOU` | `FBS_MEMBER` | `FBS` | `Big 12` | `41` | `team-041-houston` |
| 42 | `ISU` | Iowa State | `ISU` | `FBS_MEMBER` | `FBS` | `Big 12` | `42` | `team-042-iowa-state` |
| 43 | `KU` | Kansas | `KU` | `FBS_MEMBER` | `FBS` | `Big 12` | `43` | `team-043-kansas` |
| 44 | `KSU` | Kansas State | `KSU` | `FBS_MEMBER` | `FBS` | `Big 12` | `44` | `team-044-kansas-state` |
| 45 | `OKST` | Oklahoma State | `OKST` | `FBS_MEMBER` | `FBS` | `Big 12` | `45` | `team-045-oklahoma-state` |
| 46 | `TCU` | TCU | `TCU` | `FBS_MEMBER` | `FBS` | `Big 12` | `46` | `team-046-tcu` |
| 47 | `TTU` | Texas Tech | `TTU` | `FBS_MEMBER` | `FBS` | `Big 12` | `47` | `team-047-texas-tech` |
| 48 | `UCF` | UCF | `UCF` | `FBS_MEMBER` | `FBS` | `Big 12` | `48` | `team-048-ucf` |
| 49 | `UTAH` | Utah | `UTAH` | `FBS_MEMBER` | `FBS` | `Big 12` | `49` | `team-049-utah` |
| 50 | `WVU` | West Virginia | `WVU` | `FBS_MEMBER` | `FBS` | `Big 12` | `50` | `team-050-west-virginia` |
| 51 | `BC` | Boston College | `BC` | `FBS_MEMBER` | `FBS` | `ACC` | `51` | `team-051-boston-college` |
| 52 | `CAL` | California | `CAL` | `FBS_MEMBER` | `FBS` | `ACC` | `52` | `team-052-california` |
| 53 | `CLEM` | Clemson | `CLEM` | `FBS_MEMBER` | `FBS` | `ACC` | `53` | `team-053-clemson` |
| 54 | `DUKE` | Duke | `DUKE` | `FBS_MEMBER` | `FBS` | `ACC` | `54` | `team-054-duke` |
| 55 | `FSU` | Florida State | `FSU` | `FBS_MEMBER` | `FBS` | `ACC` | `55` | `team-055-florida-state` |
| 56 | `GT` | Georgia Tech | `GT` | `FBS_MEMBER` | `FBS` | `ACC` | `56` | `team-056-georgia-tech` |
| 57 | `LOU` | Louisville | `LOU` | `FBS_MEMBER` | `FBS` | `ACC` | `57` | `team-057-louisville` |
| 58 | `MIA` | Miami | `MIA` | `FBS_MEMBER` | `FBS` | `ACC` | `58` | `team-058-miami` |
| 59 | `NCSU` | NC State | `NCSU` | `FBS_MEMBER` | `FBS` | `ACC` | `59` | `team-059-nc-state` |
| 60 | `UNC` | North Carolina | `UNC` | `FBS_MEMBER` | `FBS` | `ACC` | `60` | `team-060-north-carolina` |
| 61 | `PITT` | Pittsburgh | `PITT` | `FBS_MEMBER` | `FBS` | `ACC` | `61` | `team-061-pittsburgh` |
| 62 | `SMU` | SMU | `SMU` | `FBS_MEMBER` | `FBS` | `ACC` | `62` | `team-062-smu` |
| 63 | `STAN` | Stanford | `STAN` | `FBS_MEMBER` | `FBS` | `ACC` | `63` | `team-063-stanford` |
| 64 | `SYR` | Syracuse | `SYR` | `FBS_MEMBER` | `FBS` | `ACC` | `64` | `team-064-syracuse` |
| 65 | `UVA` | Virginia | `UVA` | `FBS_MEMBER` | `FBS` | `ACC` | `65` | `team-065-virginia` |
| 66 | `VT` | Virginia Tech | `VT` | `FBS_MEMBER` | `FBS` | `ACC` | `66` | `team-066-virginia-tech` |
| 67 | `WAKE` | Wake Forest | `WAKE` | `FBS_MEMBER` | `FBS` | `ACC` | `67` | `team-067-wake-forest` |
| 68 | `BOISE` | Boise State | `BOISE` | `FBS_MEMBER` | `FBS` | `Pac-12` | `68` | `team-068-boise-state` |
| 69 | `CSU` | Colorado State | `CSU` | `FBS_MEMBER` | `FBS` | `Pac-12` | `69` | `team-069-colorado-state` |
| 70 | `FRES` | Fresno State | `FRES` | `FBS_MEMBER` | `FBS` | `Pac-12` | `70` | `team-070-fresno-state` |
| 71 | `ORST` | Oregon State | `ORST` | `FBS_MEMBER` | `FBS` | `Pac-12` | `71` | `team-071-oregon-state` |
| 72 | `SDSU` | San Diego State | `SDSU` | `FBS_MEMBER` | `FBS` | `Pac-12` | `72` | `team-072-san-diego-state` |
| 73 | `TXST` | Texas State | `TXST` | `FBS_MEMBER` | `FBS` | `Pac-12` | `73` | `team-073-texas-state` |
| 74 | `USU` | Utah State | `USU` | `FBS_MEMBER` | `FBS` | `Pac-12` | `74` | `team-074-utah-state` |
| 75 | `WSU` | Washington State | `WSU` | `FBS_MEMBER` | `FBS` | `Pac-12` | `75` | `team-075-washington-state` |
| 76 | `AF` | Air Force | `AF` | `FBS_MEMBER` | `FBS` | `Mountain West` | `76` | `team-076-air-force` |
| 77 | `HAW` | Hawaii | `HAW` | `FBS_MEMBER` | `FBS` | `Mountain West` | `77` | `team-077-hawaii` |
| 78 | `NEV` | Nevada | `NEV` | `FBS_MEMBER` | `FBS` | `Mountain West` | `78` | `team-078-nevada` |
| 79 | `NM` | New Mexico | `NM` | `FBS_MEMBER` | `FBS` | `Mountain West` | `79` | `team-079-new-mexico` |
| 80 | `NDSU` | North Dakota State | `NDSU` | `FBS_MEMBER` | `FBS` | `Mountain West` | `80` | `team-080-north-dakota-state` |
| 81 | `NIU` | Northern Illinois | `NIU` | `FBS_MEMBER` | `FBS` | `Mountain West` | `81` | `team-081-northern-illinois` |
| 82 | `SJSU` | San Jose State | `SJSU` | `FBS_MEMBER` | `FBS` | `Mountain West` | `82` | `team-082-san-jose-state` |
| 83 | `UNLV` | UNLV | `UNLV` | `FBS_MEMBER` | `FBS` | `Mountain West` | `83` | `team-083-unlv` |
| 84 | `UTEP` | UTEP | `UTEP` | `FBS_MEMBER` | `FBS` | `Mountain West` | `84` | `team-084-utep` |
| 85 | `WYO` | Wyoming | `WYO` | `FBS_MEMBER` | `FBS` | `Mountain West` | `85` | `team-085-wyoming` |
| 86 | `ARMY` | Army | `ARMY` | `FBS_MEMBER` | `FBS` | `American` | `86` | `team-086-army` |
| 87 | `ECU` | East Carolina | `ECU` | `FBS_MEMBER` | `FBS` | `American` | `87` | `team-087-east-carolina` |
| 88 | `FAU` | Florida Atlantic | `FAU` | `FBS_MEMBER` | `FBS` | `American` | `88` | `team-088-florida-atlantic` |
| 89 | `LT` | Louisiana Tech | `LT` | `FBS_MEMBER` | `FBS` | `American` | `89` | `team-089-louisiana-tech` |
| 90 | `MEM` | Memphis | `MEM` | `FBS_MEMBER` | `FBS` | `American` | `90` | `team-090-memphis` |
| 91 | `NAVY` | Navy | `NAVY` | `FBS_MEMBER` | `FBS` | `American` | `91` | `team-091-navy` |
| 92 | `NMSU` | New Mexico State | `NMSU` | `FBS_MEMBER` | `FBS` | `American` | `92` | `team-092-new-mexico-state` |
| 93 | `UNT` | North Texas | `UNT` | `FBS_MEMBER` | `FBS` | `American` | `93` | `team-093-north-texas` |
| 94 | `RICE` | Rice | `RICE` | `FBS_MEMBER` | `FBS` | `American` | `94` | `team-094-rice` |
| 95 | `USF` | South Florida | `USF` | `FBS_MEMBER` | `FBS` | `American` | `95` | `team-095-south-florida` |
| 96 | `USM` | Southern Miss | `USM` | `FBS_MEMBER` | `FBS` | `American` | `96` | `team-096-southern-miss` |
| 97 | `TEM` | Temple | `TEM` | `FBS_MEMBER` | `FBS` | `American` | `97` | `team-097-temple` |
| 98 | `TLN` | Tulane | `TLN` | `FBS_MEMBER` | `FBS` | `American` | `98` | `team-098-tulane` |
| 99 | `TLSA` | Tulsa | `TLSA` | `FBS_MEMBER` | `FBS` | `American` | `99` | `team-099-tulsa` |
| 100 | `UAB` | UAB | `UAB` | `FBS_MEMBER` | `FBS` | `American` | `100` | `team-100-uab` |
| 101 | `UTSA` | UTSA | `UTSA` | `FBS_MEMBER` | `FBS` | `American` | `101` | `team-101-utsa` |
| 102 | `BUFF` | Buffalo | `BUFF` | `FBS_MEMBER` | `FBS` | `Atlantic-8` | `102` | `team-102-buffalo` |
| 103 | `CCU` | Coastal Carolina | `CCU` | `FBS_MEMBER` | `FBS` | `Atlantic-8` | `103` | `team-103-coastal-carolina` |
| 104 | `DEL` | Delaware | `DEL` | `FBS_MEMBER` | `FBS` | `Atlantic-8` | `104` | `team-104-delaware` |
| 105 | `FIU` | Florida International | `FIU` | `FBS_MEMBER` | `FBS` | `Atlantic-8` | `105` | `team-105-florida-international` |
| 106 | `GASO` | Georgia Southern | `GASO` | `FBS_MEMBER` | `FBS` | `Atlantic-8` | `106` | `team-106-georgia-southern` |
| 107 | `GAST` | Georgia State | `GAST` | `FBS_MEMBER` | `FBS` | `Atlantic-8` | `107` | `team-107-georgia-state` |
| 108 | `MRSH` | Marshall | `MRSH` | `FBS_MEMBER` | `FBS` | `Atlantic-8` | `108` | `team-108-marshall` |
| 109 | `MTSU` | Middle Tennessee | `MTSU` | `FBS_MEMBER` | `FBS` | `Atlantic-8` | `109` | `team-109-middle-tennessee` |
| 110 | `ODU` | Old Dominion | `ODU` | `FBS_MEMBER` | `FBS` | `Atlantic-8` | `110` | `team-110-old-dominion` |
| 111 | `TROY` | Troy | `TROY` | `FBS_MEMBER` | `FBS` | `Atlantic-8` | `111` | `team-111-troy` |
| 112 | `COLG` | Colgate | `COLG` | `FBS_MEMBER` | `FBS` | `ECL` | `112` | `team-112-colgate` |
| 113 | `COR` | Cornell | `COR` | `FBS_MEMBER` | `FBS` | `ECL` | `113` | `team-113-cornell` |
| 114 | `HARV` | Harvard | `HARV` | `FBS_MEMBER` | `FBS` | `ECL` | `114` | `team-114-harvard` |
| 115 | `HC` | Holy Cross | `HC` | `FBS_MEMBER` | `FBS` | `ECL` | `115` | `team-115-holy-cross` |
| 116 | `LEH` | Lehigh | `LEH` | `FBS_MEMBER` | `FBS` | `ECL` | `116` | `team-116-lehigh` |
| 117 | `PENN` | Penn | `PENN` | `FBS_MEMBER` | `FBS` | `ECL` | `117` | `team-117-penn` |
| 118 | `PRIN` | Princeton | `PRIN` | `FBS_MEMBER` | `FBS` | `ECL` | `118` | `team-118-princeton` |
| 119 | `YALE` | Yale | `YALE` | `FBS_MEMBER` | `FBS` | `ECL` | `119` | `team-119-yale` |
| 120 | `ND` | Notre Dame | `ND` | `FBS_MEMBER` | `FBS` | `Independent` | `120` | `team-120-notre-dame` |
| 121 | `UConn` | UConn | `UConn` | `FBS_MEMBER` | `FBS` | `Independent` | `121` | `team-121-uconn` |
| 122 | `ARST` | Arkansas State | `ARST` | `SCHEDULE_ONLY_FCS` | `FCS` | `<blank>` | `<blank>` | `<blank>` |
| 123 | `CHAR` | Charlotte | `CHAR` | `SCHEDULE_ONLY_FCS` | `FCS` | `<blank>` | `<blank>` | `<blank>` |
| 124 | `CP` | Cal Poly | `CP` | `SCHEDULE_ONLY_FCS` | `FCS` | `Big Sky` | `<blank>` | `<blank>` |
| 125 | `DUQ` | Duquesne | `DUQ` | `SCHEDULE_ONLY_FCS` | `FCS` | `NEC` | `<blank>` | `<blank>` |
| 126 | `EMU` | Eastern Michigan | `EMU` | `SCHEDULE_ONLY_FCS` | `FCS` | `<blank>` | `<blank>` | `<blank>` |
| 127 | `IDHO` | Idaho | `IDHO` | `SCHEDULE_ONLY_FCS` | `FCS` | `Big Sky` | `<blank>` | `<blank>` |
| 128 | `SAC` | Sacramento State | `SAC` | `SCHEDULE_ONLY_FCS` | `FCS` | `Big Sky` | `<blank>` | `<blank>` |
| 129 | `SUU` | Southern Utah | `SUU` | `SCHEDULE_ONLY_FCS` | `FCS` | `UAC` | `<blank>` | `<blank>` |
| 130 | `TOL` | Toledo | `TOL` | `SCHEDULE_ONLY_FCS` | `FCS` | `<blank>` | `<blank>` | `<blank>` |
| 131 | `ULL` | Louisiana (UL Lafayette) | `ULL` | `SCHEDULE_ONLY_FCS` | `FCS` | `<blank>` | `<blank>` | `<blank>` |
| 132 | `ULM` | Louisiana-Monroe | `ULM` | `SCHEDULE_ONLY_FCS` | `FCS` | `<blank>` | `<blank>` | `<blank>` |
| 133 | `WKU` | Western Kentucky | `WKU` | `SCHEDULE_ONLY_FCS` | `FCS` | `<blank>` | `<blank>` | `<blank>` |
| 134 | `WMU` | Western Michigan | `WMU` | `SCHEDULE_ONLY_FCS` | `FCS` | `<blank>` | `<blank>` | `<blank>` |

## Full Canonical Records

Every source row is represented separately below. **All 35 source fields are retained.** `<blank>` is an explicit sentinel for an empty source value.

### 001 — Alabama (`ALA`)

- `master_team_id`: `1`
- `name_id`: `team-001-alabama`
- `team_name`: `Alabama`
- `abbreviated_name`: `ALA`
- `aka_name`: `<blank>`
- `schedule_id`: `ALA`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Bryant-Denny Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `7`
- `board_committee_H`: `0.752301`
- `board_power_H`: `0.757511`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_10;draft_count_mapped;portal_247_rank_18;portal_rank_mapped;talent_247_composite_sourced;talent_rank_2;talent_pts_994;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 002 — Arkansas (`ARK`)

- `master_team_id`: `2`
- `name_id`: `team-002-arkansas`
- `team_name`: `Arkansas`
- `abbreviated_name`: `ARK`
- `aka_name`: `<blank>`
- `schedule_id`: `ARK`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Donald W. Reynolds Razorback Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `13`
- `home_listed_games`: `8`
- `away_listed_games`: `5`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `82`
- `board_committee_H`: `0.39937`
- `board_power_H`: `0.400333`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_origin_unverified;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;ol_starts_unavailable;draft_2026_final;draft_picks_4;draft_count_mapped;portal_247_rank_33;portal_rank_mapped;talent_247_composite_sourced;talent_rank_23;talent_pts_773;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `schedule_count_review:13`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 003 — Auburn (`AUB`)

- `master_team_id`: `3`
- `name_id`: `team-003-auburn`
- `team_name`: `Auburn`
- `abbreviated_name`: `AUB`
- `aka_name`: `<blank>`
- `schedule_id`: `AUB`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Jordan-Hare Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `56`
- `board_committee_H`: `0.454846`
- `board_power_H`: `0.448148`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;qb_source_confirmed;returning_production_espn_sourced;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_5;draft_count_mapped;portal_247_rank_9;portal_rank_mapped;talent_247_composite_sourced;talent_rank_13;talent_pts_892;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 004 — Florida (`FLA`)

- `master_team_id`: `4`
- `name_id`: `team-004-florida`
- `team_name`: `Florida`
- `abbreviated_name`: `FLA`
- `aka_name`: `<blank>`
- `schedule_id`: `FLA`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Ben Hill Griffin Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `8`
- `away_listed_games`: `4`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `64`
- `board_committee_H`: `0.437555`
- `board_power_H`: `0.420516`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_7;draft_count_mapped;portal_247_rank_30;portal_rank_mapped;talent_247_composite_sourced;talent_rank_12;talent_pts_899;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 005 — Georgia (`UGA`)

- `master_team_id`: `5`
- `name_id`: `team-005-georgia`
- `team_name`: `Georgia`
- `abbreviated_name`: `UGA`
- `aka_name`: `<blank>`
- `schedule_id`: `UGA`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Sanford Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `1`
- `board_committee_H`: `0.815075`
- `board_power_H`: `0.81799`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_qb_confirmed;returning_production_espn_sourced;market_review_required;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_8;draft_count_mapped;portal_247_rank_16;portal_rank_mapped;talent_247_composite_sourced;talent_rank_1;talent_pts_1003;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 006 — Kentucky (`UK`)

- `master_team_id`: `6`
- `name_id`: `team-006-kentucky`
- `team_name`: `Kentucky`
- `abbreviated_name`: `UK`
- `aka_name`: `<blank>`
- `schedule_id`: `UK`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Kroger Field`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `13`
- `home_listed_games`: `7`
- `away_listed_games`: `6`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `70`
- `board_committee_H`: `0.422274`
- `board_power_H`: `0.430642`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_4;draft_count_mapped;portal_247_rank_10;portal_rank_mapped;talent_247_composite_sourced;talent_rank_27;talent_pts_763;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `schedule_count_review:13`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 007 — LSU (`LSU`)

- `master_team_id`: `7`
- `name_id`: `team-007-lsu`
- `team_name`: `LSU`
- `abbreviated_name`: `LSU`
- `aka_name`: `<blank>`
- `schedule_id`: `LSU`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Tiger Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `35`
- `board_committee_H`: `0.547825`
- `board_power_H`: `0.533973`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_asof_2026_07_01;qb_full_strength_reported;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_7;draft_count_mapped;portal_247_rank_1;portal_rank_mapped;talent_247_composite_sourced;talent_rank_6;talent_pts_920;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 008 — Mississippi State (`MSST`)

- `master_team_id`: `8`
- `name_id`: `team-008-mississippi-state`
- `team_name`: `Mississippi State`
- `abbreviated_name`: `MSST`
- `aka_name`: `<blank>`
- `schedule_id`: `MSST`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Davis Wade Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `55`
- `board_committee_H`: `0.457289`
- `board_power_H`: `0.470449`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_late_2025_starter_inferred;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_247_rank_40;portal_rank_mapped;talent_247_composite_sourced;talent_rank_24;talent_pts_770;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 009 — Missouri (`MIZ`)

- `master_team_id`: `9`
- `name_id`: `team-009-missouri`
- `team_name`: `Missouri`
- `abbreviated_name`: `MIZ`
- `aka_name`: `<blank>`
- `schedule_id`: `MIZ`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Faurot Field at Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `33`
- `board_committee_H`: `0.555547`
- `board_power_H`: `0.56198`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_source_confirmed;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_6;draft_count_mapped;portal_247_rank_20;portal_rank_mapped;talent_247_composite_sourced;talent_rank_22;talent_pts_805;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 010 — Oklahoma (`OU`)

- `master_team_id`: `10`
- `name_id`: `team-010-oklahoma`
- `team_name`: `Oklahoma`
- `abbreviated_name`: `OU`
- `aka_name`: `<blank>`
- `schedule_id`: `OU`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Gaylord Family Oklahoma Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `12`
- `board_committee_H`: `0.711369`
- `board_power_H`: `0.720741`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_qb_confirmed;returning_production_espn_sourced;availability_risk_sourced;market_review_required;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_6;draft_count_mapped;portal_247_rank_17;portal_rank_mapped;talent_247_composite_sourced;talent_rank_14;talent_pts_883;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 011 — Ole Miss (`MISS`)

- `master_team_id`: `11`
- `name_id`: `team-011-ole-miss`
- `team_name`: `Ole Miss`
- `abbreviated_name`: `MISS`
- `aka_name`: `<blank>`
- `schedule_id`: `MISS`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Vaught-Hemingway Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `11`
- `board_committee_H`: `0.717359`
- `board_power_H`: `0.727696`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_qb_confirmed;returning_production_espn_sourced;availability_risk_sourced;market_review_required;user_ruling_chambliss_cleared;oc_source_confirmed;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_247_rank_2;portal_rank_mapped;talent_247_composite_sourced;talent_rank_21;talent_pts_813;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;dc_unknown;dc_inference_retracted;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 012 — South Carolina (`SC`)

- `master_team_id`: `12`
- `name_id`: `team-012-south-carolina`
- `team_name`: `South Carolina`
- `abbreviated_name`: `SC`
- `aka_name`: `<blank>`
- `schedule_id`: `SC`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Williams-Brice Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `63`
- `board_committee_H`: `0.442401`
- `board_power_H`: `0.439016`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;returning_qb_confirmed;oc_source_confirmed;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;ol_starts_unavailable;draft_2026_final;draft_picks_3;draft_count_mapped;portal_247_rank_19;portal_rank_mapped;talent_247_composite_sourced;talent_rank_18;talent_pts_833;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 013 — Tennessee (`TENN`)

- `master_team_id`: `13`
- `name_id`: `team-013-tennessee`
- `team_name`: `Tennessee`
- `abbreviated_name`: `TENN`
- `aka_name`: `<blank>`
- `schedule_id`: `TENN`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Neyland Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `20`
- `board_committee_H`: `0.640714`
- `board_power_H`: `0.646988`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;qb_projection_athlon_sourced;dc_source_confirmed;oc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_8;ol_starts_unavailable;draft_2026_final;draft_picks_5;draft_count_mapped;portal_247_rank_26;portal_rank_mapped;talent_247_composite_sourced;talent_rank_16;talent_pts_867;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 014 — Texas (`TEX`)

- `master_team_id`: `14`
- `name_id`: `team-014-texas`
- `team_name`: `Texas`
- `abbreviated_name`: `TEX`
- `aka_name`: `<blank>`
- `schedule_id`: `TEX`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Darrell K Royal-Texas Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `2`
- `board_committee_H`: `0.813805`
- `board_power_H`: `0.816869`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_qb_confirmed;returning_production_espn_sourced;market_review_required;dc_source_confirmed;oc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_7;draft_count_mapped;portal_247_rank_3;portal_rank_mapped;talent_247_composite_sourced;talent_rank_4;talent_pts_974;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 015 — Texas A&M (`TA&M`)

- `master_team_id`: `15`
- `name_id`: `team-015-texas-a-and-m`
- `team_name`: `Texas A&M`
- `abbreviated_name`: `TA&M`
- `aka_name`: `<blank>`
- `schedule_id`: `TA&M`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Kyle Field`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `10`
- `board_committee_H`: `0.731414`
- `board_power_H`: `0.737259`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_qb_confirmed;returning_production_espn_sourced;market_review_required;oc_source_confirmed;dc_source_confirmed;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_10;draft_count_mapped;portal_247_rank_12;portal_rank_mapped;talent_247_composite_sourced;talent_rank_8;talent_pts_917;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 016 — Vanderbilt (`VAN`)

- `master_team_id`: `16`
- `name_id`: `team-016-vanderbilt`
- `team_name`: `Vanderbilt`
- `abbreviated_name`: `VAN`
- `aka_name`: `<blank>`
- `schedule_id`: `VAN`
- `2026_conference`: `SEC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `FirstBank Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `13`
- `home_listed_games`: `8`
- `away_listed_games`: `5`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `18`
- `board_committee_H`: `0.662682`
- `board_power_H`: `0.679402`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;qb_source_confirmed;returning_production_espn_sourced;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_247_rank_34;portal_rank_mapped;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_55;talent_pts_685;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `schedule_count_review:13`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `SEC`
- `source_fcs_reference`: `<blank>`

### 017 — Illinois (`ILL`)

- `master_team_id`: `17`
- `name_id`: `team-017-illinois`
- `team_name`: `Illinois`
- `abbreviated_name`: `ILL`
- `aka_name`: `<blank>`
- `schedule_id`: `ILL`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `21`
- `board_committee_H`: `0.630989`
- `board_power_H`: `0.633241`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;qb_source_confirmed;returning_production_espn_sourced;qb_projection_athlon_sourced;dc_source_confirmed;oc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_3;draft_count_mapped;portal_247_rank_43;portal_rank_mapped;talent_247_composite_sourced;talent_rank_64;talent_pts_662;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 018 — Indiana (`IU`)

- `master_team_id`: `18`
- `name_id`: `team-018-indiana`
- `team_name`: `Indiana`
- `abbreviated_name`: `IU`
- `aka_name`: `<blank>`
- `schedule_id`: `IU`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `6`
- `board_committee_H`: `0.775899`
- `board_power_H`: `0.767382`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;qb_source_confirmed;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_8;draft_count_mapped;portal_247_rank_8;portal_rank_mapped;talent_247_composite_sourced;talent_rank_72;talent_pts_645;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 019 — Iowa (`IOWA`)

- `master_team_id`: `19`
- `name_id`: `team-019-iowa`
- `team_name`: `Iowa`
- `abbreviated_name`: `IOWA`
- `aka_name`: `<blank>`
- `schedule_id`: `IOWA`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Kinnick Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `16`
- `board_committee_H`: `0.684258`
- `board_power_H`: `0.691483`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_7;draft_count_mapped;portal_outside_top50;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_42;talent_pts_710;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 020 — Maryland (`MD`)

- `master_team_id`: `20`
- `name_id`: `team-020-maryland`
- `team_name`: `Maryland`
- `abbreviated_name`: `MD`
- `aka_name`: `<blank>`
- `schedule_id`: `MD`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `SECU Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `46`
- `board_committee_H`: `0.480828`
- `board_power_H`: `0.495953`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;returning_qb_confirmed;oc_source_confirmed;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_52;talent_pts_699;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 021 — Michigan (`MICH`)

- `master_team_id`: `21`
- `name_id`: `team-021-michigan`
- `team_name`: `Michigan`
- `abbreviated_name`: `MICH`
- `aka_name`: `<blank>`
- `schedule_id`: `MICH`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Michigan Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `17`
- `board_committee_H`: `0.672063`
- `board_power_H`: `0.669347`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_qb_confirmed;returning_production_espn_sourced;market_review_required;oc_source_confirmed;dc_source_confirmed;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_6;draft_count_mapped;portal_247_rank_24;portal_rank_mapped;talent_247_composite_sourced;talent_rank_11;talent_pts_907;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 022 — Michigan State (`MSU`)

- `master_team_id`: `22`
- `name_id`: `team-022-michigan-state`
- `team_name`: `Michigan State`
- `abbreviated_name`: `MSU`
- `aka_name`: `Michigan St.`
- `schedule_id`: `MSU`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Spartan Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `98`
- `board_committee_H`: `0.354662`
- `board_power_H`: `0.360015`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;qb_projection_athlon_sourced;oc_source_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_38;talent_pts_717;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;dc_unknown;dc_inference_retracted;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 023 — Minnesota (`MINN`)

- `master_team_id`: `23`
- `name_id`: `team-023-minnesota`
- `team_name`: `Minnesota`
- `abbreviated_name`: `MINN`
- `aka_name`: `<blank>`
- `schedule_id`: `MINN`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Huntington Bank Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `31`
- `board_committee_H`: `0.560118`
- `board_power_H`: `0.572607`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;returning_qb_confirmed;oc_continuity_inferred;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_41;talent_pts_711;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 024 — Nebraska (`NEB`)

- `master_team_id`: `24`
- `name_id`: `team-024-nebraska`
- `team_name`: `Nebraska`
- `abbreviated_name`: `NEB`
- `aka_name`: `<blank>`
- `schedule_id`: `NEB`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `39`
- `board_committee_H`: `0.519728`
- `board_power_H`: `0.521643`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;dc_source_confirmed;oc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_247_rank_31;portal_rank_mapped;talent_247_composite_sourced;talent_rank_20;talent_pts_821;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 025 — Northwestern (`NU`)

- `master_team_id`: `25`
- `name_id`: `team-025-northwestern`
- `team_name`: `Northwestern`
- `abbreviated_name`: `NU`
- `aka_name`: `<blank>`
- `schedule_id`: `NU`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Ryan Field`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `72`
- `board_committee_H`: `0.420313`
- `board_power_H`: `0.426334`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;qb_projection_athlon_sourced;oc_source_confirmed;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_247_rank_42;portal_rank_mapped;talent_247_composite_sourced;talent_rank_57;talent_pts_678;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 026 — Ohio State (`OSU`)

- `master_team_id`: `26`
- `name_id`: `team-026-ohio-state`
- `team_name`: `Ohio State`
- `abbreviated_name`: `OSU`
- `aka_name`: `Ohio St.`
- `schedule_id`: `OSU`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Ohio Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `8`
- `board_committee_H`: `0.751059`
- `board_power_H`: `0.748607`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;market_review_required;returning_qb_confirmed;oc_source_confirmed;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_8;ol_starts_unavailable;draft_2026_final;draft_picks_11;draft_count_mapped;portal_247_rank_7;portal_rank_mapped;talent_247_composite_sourced;talent_rank_3;talent_pts_974;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 027 — Oregon (`ORE`)

- `master_team_id`: `27`
- `name_id`: `team-027-oregon`
- `team_name`: `Oregon`
- `abbreviated_name`: `ORE`
- `aka_name`: `<blank>`
- `schedule_id`: `ORE`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Autzen Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `4`
- `board_committee_H`: `0.784212`
- `board_power_H`: `0.776604`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_qb_confirmed;returning_production_espn_sourced;market_review_required;oc_source_confirmed;dc_source_confirmed;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_7;ol_starts_unavailable;draft_2026_final;draft_picks_7;draft_count_mapped;portal_247_rank_21;portal_rank_mapped;talent_247_composite_sourced;talent_rank_5;talent_pts_941;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 028 — Penn State (`PSU`)

- `master_team_id`: `28`
- `name_id`: `team-028-penn-state`
- `team_name`: `Penn State`
- `abbreviated_name`: `PSU`
- `aka_name`: `Penn St.`
- `schedule_id`: `PSU`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Beaver Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `62`
- `board_committee_H`: `0.449954`
- `board_power_H`: `0.426379`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_8;draft_count_mapped;portal_247_rank_4;portal_rank_mapped;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_10;talent_pts_910;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 029 — Purdue (`PUR`)

- `master_team_id`: `29`
- `name_id`: `team-029-purdue`
- `team_name`: `Purdue`
- `abbreviated_name`: `PUR`
- `aka_name`: `<blank>`
- `schedule_id`: `PUR`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Ross-Ade Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `58`
- `board_committee_H`: `0.452238`
- `board_power_H`: `0.472915`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;returning_qb_confirmed;oc_continuity_inferred;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_247_rank_48;portal_rank_mapped;talent_247_composite_sourced;talent_rank_54;talent_pts_688;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 030 — Rutgers (`RUTG`)

- `master_team_id`: `30`
- `name_id`: `team-030-rutgers`
- `team_name`: `Rutgers`
- `abbreviated_name`: `RUTG`
- `aka_name`: `<blank>`
- `schedule_id`: `RUTG`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `SHI Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `91`
- `board_committee_H`: `0.37174`
- `board_power_H`: `0.383392`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;qb_projection_athlon_sourced;dc_source_confirmed;oc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_53;talent_pts_689;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 031 — UCLA (`UCLA`)

- `master_team_id`: `31`
- `name_id`: `team-031-ucla`
- `team_name`: `UCLA`
- `abbreviated_name`: `UCLA`
- `aka_name`: `<blank>`
- `schedule_id`: `UCLA`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Rose Bowl`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `65`
- `board_committee_H`: `0.433561`
- `board_power_H`: `0.424513`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;returning_qb_confirmed;oc_source_confirmed;dc_source_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_247_rank_25;portal_rank_mapped;talent_247_composite_sourced;talent_rank_26;talent_pts_767;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 032 — USC (`USC`)

- `master_team_id`: `32`
- `name_id`: `team-032-usc`
- `team_name`: `USC`
- `abbreviated_name`: `USC`
- `aka_name`: `<blank>`
- `schedule_id`: `USC`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Los Angeles Memorial Coliseum`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `13`
- `board_committee_H`: `0.708553`
- `board_power_H`: `0.710997`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_qb_confirmed;qb_name_unsourced_returning_confirmed;returning_production_espn_sourced;dc_source_confirmed;oc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_9;ol_starts_unavailable;draft_2026_final;draft_picks_3;draft_count_mapped;portal_247_rank_29;portal_rank_mapped;talent_247_composite_sourced;talent_rank_17;talent_pts_848;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 033 — Washington (`WASH`)

- `master_team_id`: `33`
- `name_id`: `team-033-washington`
- `team_name`: `Washington`
- `abbreviated_name`: `WASH`
- `aka_name`: `<blank>`
- `schedule_id`: `WASH`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Husky Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `19`
- `board_committee_H`: `0.656521`
- `board_power_H`: `0.662142`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_qb_confirmed;returning_production_espn_sourced;oc_continuity_inferred;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_7;ol_starts_unavailable;draft_2026_final;draft_picks_7;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_37;talent_pts_721;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 034 — Wisconsin (`WIS`)

- `master_team_id`: `34`
- `name_id`: `team-034-wisconsin`
- `team_name`: `Wisconsin`
- `abbreviated_name`: `WIS`
- `aka_name`: `<blank>`
- `schedule_id`: `WIS`
- `2026_conference`: `Big Ten`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Camp Randall Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `41`
- `board_committee_H`: `0.504791`
- `board_power_H`: `0.507112`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_247_rank_38;portal_rank_mapped;talent_247_composite_sourced;talent_rank_28;talent_pts_763;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big Ten`
- `source_fcs_reference`: `<blank>`

### 035 — Arizona (`ARIZ`)

- `master_team_id`: `35`
- `name_id`: `team-035-arizona`
- `team_name`: `Arizona`
- `abbreviated_name`: `ARIZ`
- `aka_name`: `<blank>`
- `schedule_id`: `ARIZ`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Arizona Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `25`
- `board_committee_H`: `0.604285`
- `board_power_H`: `0.60363`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;returning_qb_confirmed;oc_continuity_inferred;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_4;draft_count_mapped;portal_247_rank_49;portal_rank_mapped;talent_247_composite_sourced;talent_rank_67;talent_pts_652;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 036 — Arizona State (`ASU`)

- `master_team_id`: `36`
- `name_id`: `team-036-arizona-state`
- `team_name`: `Arizona State`
- `abbreviated_name`: `ASU`
- `aka_name`: `<blank>`
- `schedule_id`: `ASU`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Mountain America Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `44`
- `board_committee_H`: `0.487429`
- `board_power_H`: `0.487061`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_qb_confirmed;returning_production_espn_sourced;availability_risk_sourced;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_0;ol_starts_unavailable;draft_2026_final;draft_picks_4;draft_count_mapped;portal_247_rank_22;portal_rank_mapped;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_33;talent_pts_739;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 037 — BYU (`BYU`)

- `master_team_id`: `37`
- `name_id`: `team-037-byu`
- `team_name`: `BYU`
- `abbreviated_name`: `BYU`
- `aka_name`: `<blank>`
- `schedule_id`: `BYU`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `LaVell Edwards Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `8`
- `away_listed_games`: `4`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `14`
- `board_committee_H`: `0.706947`
- `board_power_H`: `0.705702`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_qb_confirmed;returning_production_espn_sourced;dc_source_confirmed;oc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_247_rank_39;portal_rank_mapped;talent_247_composite_sourced;talent_rank_70;talent_pts_649;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 038 — Baylor (`BAY`)

- `master_team_id`: `38`
- `name_id`: `team-038-baylor`
- `team_name`: `Baylor`
- `abbreviated_name`: `BAY`
- `aka_name`: `<blank>`
- `schedule_id`: `BAY`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `McLane Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `57`
- `board_committee_H`: `0.454718`
- `board_power_H`: `0.458086`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;qb_projection_athlon_sourced;dc_source_confirmed;oc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_247_rank_36;portal_rank_mapped;talent_247_composite_sourced;talent_rank_35;talent_pts_726;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 039 — Cincinnati (`CIN`)

- `master_team_id`: `39`
- `name_id`: `team-039-cincinnati`
- `team_name`: `Cincinnati`
- `abbreviated_name`: `CIN`
- `aka_name`: `<blank>`
- `schedule_id`: `CIN`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Nippert Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `52`
- `board_committee_H`: `0.462925`
- `board_power_H`: `0.465591`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_4;draft_count_mapped;portal_247_rank_41;portal_rank_mapped;talent_247_composite_sourced;talent_rank_73;talent_pts_644;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 040 — Colorado (`COLO`)

- `master_team_id`: `40`
- `name_id`: `team-040-colorado`
- `team_name`: `Colorado`
- `abbreviated_name`: `COLO`
- `aka_name`: `<blank>`
- `schedule_id`: `COLO`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Folsom Field`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `67`
- `board_committee_H`: `0.428668`
- `board_power_H`: `0.434499`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;qb_late_2025_starter_inferred;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_247_rank_23;portal_rank_mapped;talent_247_composite_sourced;talent_rank_30;talent_pts_755;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 041 — Houston (`HOU`)

- `master_team_id`: `41`
- `name_id`: `team-041-houston`
- `team_name`: `Houston`
- `abbreviated_name`: `HOU`
- `aka_name`: `<blank>`
- `schedule_id`: `HOU`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `TDECU Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `24`
- `board_committee_H`: `0.623098`
- `board_power_H`: `0.629118`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;returning_qb_confirmed;oc_continuity_inferred;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_247_rank_50;portal_rank_mapped;talent_247_composite_sourced;talent_rank_66;talent_pts_657;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 042 — Iowa State (`ISU`)

- `master_team_id`: `42`
- `name_id`: `team-042-iowa-state`
- `team_name`: `Iowa State`
- `abbreviated_name`: `ISU`
- `aka_name`: `Iowa St.`
- `schedule_id`: `ISU`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Jack Trice Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `106`
- `board_committee_H`: `0.332824`
- `board_power_H`: `0.325333`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;qb_source_confirmed;returning_production_espn_sourced;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_0;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_71;talent_pts_649;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 043 — Kansas (`KU`)

- `master_team_id`: `43`
- `name_id`: `team-043-kansas`
- `team_name`: `Kansas`
- `abbreviated_name`: `KU`
- `aka_name`: `<blank>`
- `schedule_id`: `KU`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `David Booth Kansas Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `43`
- `board_committee_H`: `0.495464`
- `board_power_H`: `0.513333`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;oc_source_confirmed;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_48;talent_pts_705;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 044 — Kansas State (`KSU`)

- `master_team_id`: `44`
- `name_id`: `team-044-kansas-state`
- `team_name`: `Kansas State`
- `abbreviated_name`: `KSU`
- `aka_name`: `Kansas St.`
- `schedule_id`: `KSU`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Bill Snyder Family Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `80`
- `board_committee_H`: `0.403419`
- `board_power_H`: `0.378797`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;returning_qb_confirmed;oc_source_confirmed;dc_source_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_247_rank_45;portal_rank_mapped;talent_247_composite_sourced;talent_rank_47;talent_pts_706;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 045 — Oklahoma State (`OKST`)

- `master_team_id`: `45`
- `name_id`: `team-045-oklahoma-state`
- `team_name`: `Oklahoma State`
- `abbreviated_name`: `OKST`
- `aka_name`: `Oklahoma St.`
- `schedule_id`: `OKST`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Boone Pickens Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `47`
- `board_committee_H`: `0.479665`
- `board_power_H`: `0.484081`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;qb_source_confirmed;returning_production_espn_sourced;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_247_rank_15;portal_rank_mapped;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_49;talent_pts_703;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 046 — TCU (`TCU`)

- `master_team_id`: `46`
- `name_id`: `team-046-tcu`
- `team_name`: `TCU`
- `abbreviated_name`: `TCU`
- `aka_name`: `<blank>`
- `schedule_id`: `TCU`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Amon G. Carter Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `28`
- `board_committee_H`: `0.582723`
- `board_power_H`: `0.59371`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;qb_projection_athlon_sourced;oc_source_confirmed;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_3;draft_count_mapped;portal_247_rank_47;portal_rank_mapped;talent_247_composite_sourced;talent_rank_32;talent_pts_745;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 047 — Texas Tech (`TTU`)

- `master_team_id`: `47`
- `name_id`: `team-047-texas-tech`
- `team_name`: `Texas Tech`
- `abbreviated_name`: `TTU`
- `aka_name`: `<blank>`
- `schedule_id`: `TTU`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Jones AT&T Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `5`
- `board_committee_H`: `0.778288`
- `board_power_H`: `0.771818`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;qb_source_confirmed;returning_production_espn_sourced;availability_risk_sourced;market_review_required;market_line_moved_post_open;user_ruling_sorsby_out;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;sorsby_supplemental_draft_confirmed;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_9;draft_count_mapped;portal_247_rank_6;portal_rank_mapped;talent_247_composite_sourced;talent_rank_29;talent_pts_757;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 048 — UCF (`UCF`)

- `master_team_id`: `48`
- `name_id`: `team-048-ucf`
- `team_name`: `UCF`
- `abbreviated_name`: `UCF`
- `aka_name`: `Central Florida`
- `schedule_id`: `UCF`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `FBC Mortgage Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `53`
- `board_committee_H`: `0.461478`
- `board_power_H`: `0.463691`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_43;talent_pts_710;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 049 — Utah (`UTAH`)

- `master_team_id`: `49`
- `name_id`: `team-049-utah`
- `team_name`: `Utah`
- `abbreviated_name`: `UTAH`
- `aka_name`: `<blank>`
- `schedule_id`: `UTAH`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Rice-Eccles Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `22`
- `board_committee_H`: `0.629259`
- `board_power_H`: `0.62625`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;returning_qb_confirmed;oc_source_confirmed;dc_source_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_3;draft_count_mapped;portal_247_rank_44;portal_rank_mapped;talent_247_composite_sourced;talent_rank_44;talent_pts_708;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 050 — West Virginia (`WVU`)

- `master_team_id`: `50`
- `name_id`: `team-050-west-virginia`
- `team_name`: `West Virginia`
- `abbreviated_name`: `WVU`
- `aka_name`: `<blank>`
- `schedule_id`: `WVU`
- `2026_conference`: `Big 12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Milan Puskar Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `13`
- `home_listed_games`: `7`
- `away_listed_games`: `6`
- `neutral_site_games`: `2`
- `conference_games`: `9`
- `board_rank_H`: `93`
- `board_committee_H`: `0.363504`
- `board_power_H`: `0.359387`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;qb_origin_unverified;returning_qb_confirmed;oc_continuity_inferred;dc_continuity_inferred;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_63;talent_pts_662;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `schedule_count_review:13`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Big 12`
- `source_fcs_reference`: `<blank>`

### 051 — Boston College (`BC`)

- `master_team_id`: `51`
- `name_id`: `team-051-boston-college`
- `team_name`: `Boston College`
- `abbreviated_name`: `BC`
- `aka_name`: `BC`
- `schedule_id`: `BC`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Alumni Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `81`
- `board_committee_H`: `0.402752`
- `board_power_H`: `0.417909`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;market_review_required;qb_late_2025_starter_inferred;returning_qb_confirmed;dc_source_confirmed;oc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_4;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_69;talent_pts_650;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 052 — California (`CAL`)

- `master_team_id`: `52`
- `name_id`: `team-052-california`
- `team_name`: `California`
- `abbreviated_name`: `CAL`
- `aka_name`: `<blank>`
- `schedule_id`: `CAL`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `California Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `49`
- `board_committee_H`: `0.474849`
- `board_power_H`: `0.470444`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_qb_confirmed;returning_production_espn_sourced;market_review_required;oc_source_confirmed;dc_source_confirmed;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_247_rank_14;portal_rank_mapped;talent_247_composite_sourced;talent_rank_36;talent_pts_726;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 053 — Clemson (`CLEM`)

- `master_team_id`: `53`
- `name_id`: `team-053-clemson`
- `team_name`: `Clemson`
- `abbreviated_name`: `CLEM`
- `aka_name`: `<blank>`
- `schedule_id`: `CLEM`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `51`
- `board_committee_H`: `0.466358`
- `board_power_H`: `0.455349`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_source_confirmed;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;ol_starts_unavailable;draft_2026_final;draft_picks_9;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_7;talent_pts_918;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 054 — Duke (`DUKE`)

- `master_team_id`: `54`
- `name_id`: `team-054-duke`
- `team_name`: `Duke`
- `abbreviated_name`: `DUKE`
- `aka_name`: `<blank>`
- `schedule_id`: `DUKE`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Wallace Wade Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `40`
- `board_committee_H`: `0.510583`
- `board_power_H`: `0.516025`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_3;draft_count_mapped;portal_outside_top50;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_58;talent_pts_669;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 055 — Florida State (`FSU`)

- `master_team_id`: `55`
- `name_id`: `team-055-florida-state`
- `team_name`: `Florida State`
- `abbreviated_name`: `FSU`
- `aka_name`: `Florida St`
- `schedule_id`: `FSU`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Doak Campbell Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `48`
- `board_committee_H`: `0.478297`
- `board_power_H`: `0.476502`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_source_confirmed;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_247_rank_28;portal_rank_mapped;talent_247_composite_sourced;talent_rank_19;talent_pts_828;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 056 — Georgia Tech (`GT`)

- `master_team_id`: `56`
- `name_id`: `team-056-georgia-tech`
- `team_name`: `Georgia Tech`
- `abbreviated_name`: `GT`
- `aka_name`: `<blank>`
- `schedule_id`: `GT`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Bobby Dodd Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `26`
- `board_committee_H`: `0.599353`
- `board_power_H`: `0.605378`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_source_confirmed;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_247_rank_35;portal_rank_mapped;talent_247_composite_sourced;talent_rank_39;talent_pts_716;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 057 — Louisville (`LOU`)

- `master_team_id`: `57`
- `name_id`: `team-057-louisville`
- `team_name`: `Louisville`
- `abbreviated_name`: `LOU`
- `aka_name`: `<blank>`
- `schedule_id`: `LOU`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `L&N Federal Credit Union Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `37`
- `board_committee_H`: `0.543038`
- `board_power_H`: `0.536788`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;dc_source_confirmed;oc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_247_rank_13;portal_rank_mapped;talent_247_composite_sourced;talent_rank_50;talent_pts_701;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 058 — Miami (`MIA`)

- `master_team_id`: `58`
- `name_id`: `team-058-miami`
- `team_name`: `Miami`
- `abbreviated_name`: `MIA`
- `aka_name`: `<blank>`
- `schedule_id`: `MIA`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Hard Rock Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `3`
- `board_committee_H`: `0.802912`
- `board_power_H`: `0.796767`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;qb_source_confirmed;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_9;draft_count_mapped;portal_247_rank_5;portal_rank_mapped;talent_247_composite_sourced;talent_rank_15;talent_pts_875;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 059 — NC State (`NCSU`)

- `master_team_id`: `59`
- `name_id`: `team-059-nc-state`
- `team_name`: `NC State`
- `abbreviated_name`: `NCSU`
- `aka_name`: `NC St.`
- `schedule_id`: `NCSU`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Carter-Finley Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `34`
- `board_committee_H`: `0.554127`
- `board_power_H`: `0.552959`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;market_review_required;returning_qb_confirmed;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_247_rank_46;portal_rank_mapped;talent_247_composite_sourced;talent_rank_45;talent_pts_708;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 060 — North Carolina (`UNC`)

- `master_team_id`: `60`
- `name_id`: `team-060-north-carolina`
- `team_name`: `North Carolina`
- `abbreviated_name`: `UNC`
- `aka_name`: `<blank>`
- `schedule_id`: `UNC`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Kenan Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `1`
- `conference_games`: `8`
- `board_rank_H`: `54`
- `board_committee_H`: `0.457368`
- `board_power_H`: `0.471257`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_source_confirmed;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_31;talent_pts_753;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 061 — Pittsburgh (`PITT`)

- `master_team_id`: `61`
- `name_id`: `team-061-pittsburgh`
- `team_name`: `Pittsburgh`
- `abbreviated_name`: `PITT`
- `aka_name`: `<blank>`
- `schedule_id`: `PITT`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Acrisure Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `29`
- `board_committee_H`: `0.563658`
- `board_power_H`: `0.564913`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;market_review_required;returning_qb_confirmed;dc_source_confirmed;oc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_56;talent_pts_681;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 062 — SMU (`SMU`)

- `master_team_id`: `62`
- `name_id`: `team-062-smu`
- `team_name`: `SMU`
- `abbreviated_name`: `SMU`
- `aka_name`: `<blank>`
- `schedule_id`: `SMU`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Gerald J. Ford Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `23`
- `board_committee_H`: `0.626309`
- `board_power_H`: `0.622525`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;returning_qb_confirmed;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_247_rank_32;portal_rank_mapped;talent_247_composite_sourced;talent_rank_25;talent_pts_767;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 063 — Stanford (`STAN`)

- `master_team_id`: `63`
- `name_id`: `team-063-stanford`
- `team_name`: `Stanford`
- `abbreviated_name`: `STAN`
- `aka_name`: `<blank>`
- `schedule_id`: `STAN`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Stanford Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `89`
- `board_committee_H`: `0.378603`
- `board_power_H`: `0.391862`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_46;talent_pts_707;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 064 — Syracuse (`SYR`)

- `master_team_id`: `64`
- `name_id`: `team-064-syracuse`
- `team_name`: `Syracuse`
- `abbreviated_name`: `SYR`
- `aka_name`: `<blank>`
- `schedule_id`: `SYR`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `JMA Wireless Dome`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `50`
- `board_committee_H`: `0.470961`
- `board_power_H`: `0.483504`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_injury_recovery_achilles;returning_qb_confirmed;dc_source_confirmed;oc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_34;talent_pts_728;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 065 — Virginia (`UVA`)

- `master_team_id`: `65`
- `name_id`: `team-065-virginia`
- `team_name`: `Virginia`
- `abbreviated_name`: `UVA`
- `aka_name`: `<blank>`
- `schedule_id`: `UVA`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Scott Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `1`
- `conference_games`: `9`
- `board_rank_H`: `15`
- `board_committee_H`: `0.698316`
- `board_power_H`: `0.712825`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_247_rank_37;portal_rank_mapped;talent_247_composite_sourced;talent_rank_62;talent_pts_667;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 066 — Virginia Tech (`VT`)

- `master_team_id`: `66`
- `name_id`: `team-066-virginia-tech`
- `team_name`: `Virginia Tech`
- `abbreviated_name`: `VT`
- `aka_name`: `<blank>`
- `schedule_id`: `VT`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Lane Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `61`
- `board_committee_H`: `0.450896`
- `board_power_H`: `0.445032`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_source_confirmed;dc_source_confirmed;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_8;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_247_rank_27;portal_rank_mapped;talent_247_composite_sourced;talent_rank_40;talent_pts_712;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 067 — Wake Forest (`WAKE`)

- `master_team_id`: `67`
- `name_id`: `team-067-wake-forest`
- `team_name`: `Wake Forest`
- `abbreviated_name`: `WAKE`
- `aka_name`: `<blank>`
- `schedule_id`: `WAKE`
- `2026_conference`: `ACC`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `1`
- `g5_flag`: `0`
- `independent_flag`: `0`
- `stadium`: `Allegacy Federal Credit Union Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `38`
- `board_committee_H`: `0.521408`
- `board_power_H`: `0.532707`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_production_espn_sourced;market_review_required;qb_projection_athlon_sourced;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_74;talent_pts_627;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ACC`
- `source_fcs_reference`: `<blank>`

### 068 — Boise State (`BOISE`)

- `master_team_id`: `68`
- `name_id`: `team-068-boise-state`
- `team_name`: `Boise State`
- `abbreviated_name`: `BOISE`
- `aka_name`: `Boise St.`
- `schedule_id`: `BOISE`
- `2026_conference`: `Pac-12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Albertsons Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `42`
- `board_committee_H`: `0.498321`
- `board_power_H`: `0.481513`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;pac12_g5_2026;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_7;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_81;talent_pts_611;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Pac-12`
- `source_fcs_reference`: `<blank>`

### 069 — Colorado State (`CSU`)

- `master_team_id`: `69`
- `name_id`: `team-069-colorado-state`
- `team_name`: `Colorado State`
- `abbreviated_name`: `CSU`
- `aka_name`: `Colorado St.`
- `schedule_id`: `CSU`
- `2026_conference`: `Pac-12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Canvas Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `120`
- `board_committee_H`: `0.277516`
- `board_power_H`: `0.275391`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;pac12_g5_2026;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_92;talent_pts_584;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Pac-12`
- `source_fcs_reference`: `<blank>`

### 070 — Fresno State (`FRES`)

- `master_team_id`: `70`
- `name_id`: `team-070-fresno-state`
- `team_name`: `Fresno State`
- `abbreviated_name`: `FRES`
- `aka_name`: `Fresno St.`
- `schedule_id`: `FRES`
- `2026_conference`: `Pac-12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Valley Children's Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `83`
- `board_committee_H`: `0.389081`
- `board_power_H`: `0.366581`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;pac12_g5_2026;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_90;talent_pts_587;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Pac-12`
- `source_fcs_reference`: `<blank>`

### 071 — Oregon State (`ORST`)

- `master_team_id`: `71`
- `name_id`: `team-071-oregon-state`
- `team_name`: `Oregon State`
- `abbreviated_name`: `ORST`
- `aka_name`: `Oregon St.`
- `schedule_id`: `ORST`
- `2026_conference`: `Pac-12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Reser Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `115`
- `board_committee_H`: `0.298899`
- `board_power_H`: `0.299182`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;pac12_g5_2026;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_60;talent_pts_668;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Pac-12`
- `source_fcs_reference`: `<blank>`

### 072 — San Diego State (`SDSU`)

- `master_team_id`: `72`
- `name_id`: `team-072-san-diego-state`
- `team_name`: `San Diego State`
- `abbreviated_name`: `SDSU`
- `aka_name`: `San Diego St.`
- `schedule_id`: `SDSU`
- `2026_conference`: `Pac-12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Snapdragon Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `77`
- `board_committee_H`: `0.411422`
- `board_power_H`: `0.390458`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;pac12_g5_2026;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_continuity_inferred;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_7;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_86;talent_pts_594;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Pac-12`
- `source_fcs_reference`: `<blank>`

### 073 — Texas State (`TXST`)

- `master_team_id`: `73`
- `name_id`: `team-073-texas-state`
- `team_name`: `Texas State`
- `abbreviated_name`: `TXST`
- `aka_name`: `Texas St.`
- `schedule_id`: `TXST`
- `2026_conference`: `Pac-12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `UFCU Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `87`
- `board_committee_H`: `0.380325`
- `board_power_H`: `0.364913`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;pac12_g5_2026;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_76;talent_pts_612;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Pac-12`
- `source_fcs_reference`: `<blank>`

### 074 — Utah State (`USU`)

- `master_team_id`: `74`
- `name_id`: `team-074-utah-state`
- `team_name`: `Utah State`
- `abbreviated_name`: `USU`
- `aka_name`: `Utah St.`
- `schedule_id`: `USU`
- `2026_conference`: `Pac-12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Maverik Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `90`
- `board_committee_H`: `0.378584`
- `board_power_H`: `0.378788`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;pac12_g5_2026;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Pac-12`
- `source_fcs_reference`: `<blank>`

### 075 — Washington State (`WSU`)

- `master_team_id`: `75`
- `name_id`: `team-075-washington-state`
- `team_name`: `Washington State`
- `abbreviated_name`: `WSU`
- `aka_name`: `Washington St.`
- `schedule_id`: `WSU`
- `2026_conference`: `Pac-12`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Gesa Field at Martin Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `107`
- `board_committee_H`: `0.33152`
- `board_power_H`: `0.326927`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;pac12_g5_2026;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_95;talent_pts_569;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Pac-12`
- `source_fcs_reference`: `<blank>`

### 076 — Air Force (`AF`)

- `master_team_id`: `76`
- `name_id`: `team-076-air-force`
- `team_name`: `Air Force`
- `abbreviated_name`: `AF`
- `aka_name`: `<blank>`
- `schedule_id`: `AF`
- `2026_conference`: `Mountain West`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Falcon Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `92`
- `board_committee_H`: `0.367694`
- `board_power_H`: `0.354465`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_continuity_inferred;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Mountain West`
- `source_fcs_reference`: `<blank>`

### 077 — Hawaii (`HAW`)

- `master_team_id`: `77`
- `name_id`: `team-077-hawaii`
- `team_name`: `Hawaii`
- `abbreviated_name`: `HAW`
- `aka_name`: `Hawai'i`
- `schedule_id`: `HAW`
- `2026_conference`: `Mountain West`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Clarence T.C. Ching Athletics Complex`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `88`
- `board_committee_H`: `0.379427`
- `board_power_H`: `0.358853`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Mountain West`
- `source_fcs_reference`: `<blank>`

### 078 — Nevada (`NEV`)

- `master_team_id`: `78`
- `name_id`: `team-078-nevada`
- `team_name`: `Nevada`
- `abbreviated_name`: `NEV`
- `aka_name`: `<blank>`
- `schedule_id`: `NEV`
- `2026_conference`: `Mountain West`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Mackay Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `86`
- `board_committee_H`: `0.384319`
- `board_power_H`: `0.390175`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Mountain West`
- `source_fcs_reference`: `<blank>`

### 079 — New Mexico (`NM`)

- `master_team_id`: `79`
- `name_id`: `team-079-new-mexico`
- `team_name`: `New Mexico`
- `abbreviated_name`: `NM`
- `aka_name`: `<blank>`
- `schedule_id`: `NM`
- `2026_conference`: `Mountain West`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `University Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `68`
- `board_committee_H`: `0.428393`
- `board_power_H`: `0.420471`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_continuity_inferred;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_7;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Mountain West`
- `source_fcs_reference`: `<blank>`

### 080 — North Dakota State (`NDSU`)

- `master_team_id`: `80`
- `name_id`: `team-080-north-dakota-state`
- `team_name`: `North Dakota State`
- `abbreviated_name`: `NDSU`
- `aka_name`: `<blank>`
- `schedule_id`: `NDSU`
- `2026_conference`: `Mountain West`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Fargodome`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `79`
- `board_committee_H`: `0.403423`
- `board_power_H`: `0.40043`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;ndsu_mwc_synthetic_member;synthetic_conference_rule_applied;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;market_data_unavailable;qb_projection_athlon_sourced;market_not_posted_fbs_newcomer;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Mountain West`
- `source_fcs_reference`: `<blank>`

### 081 — Northern Illinois (`NIU`)

- `master_team_id`: `81`
- `name_id`: `team-081-northern-illinois`
- `team_name`: `Northern Illinois`
- `abbreviated_name`: `NIU`
- `aka_name`: `<blank>`
- `schedule_id`: `NIU`
- `2026_conference`: `Mountain West`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Huskie Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `84`
- `board_committee_H`: `0.387674`
- `board_power_H`: `0.399984`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Mountain West`
- `source_fcs_reference`: `<blank>`

### 082 — San Jose State (`SJSU`)

- `master_team_id`: `82`
- `name_id`: `team-082-san-jose-state`
- `team_name`: `San Jose State`
- `abbreviated_name`: `SJSU`
- `aka_name`: `San Jose St.`
- `schedule_id`: `SJSU`
- `2026_conference`: `Mountain West`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `CEFCU Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `108`
- `board_committee_H`: `0.32717`
- `board_power_H`: `0.31587`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Mountain West`
- `source_fcs_reference`: `<blank>`

### 083 — UNLV (`UNLV`)

- `master_team_id`: `83`
- `name_id`: `team-083-unlv`
- `team_name`: `UNLV`
- `abbreviated_name`: `UNLV`
- `aka_name`: `<blank>`
- `schedule_id`: `UNLV`
- `2026_conference`: `Mountain West`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Allegiant Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `101`
- `board_committee_H`: `0.352792`
- `board_power_H`: `0.329835`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;portal_qb_gain_sourced;talent_247_composite_sourced;talent_rank_51;talent_pts_701;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Mountain West`
- `source_fcs_reference`: `<blank>`

### 084 — UTEP (`UTEP`)

- `master_team_id`: `84`
- `name_id`: `team-084-utep`
- `team_name`: `UTEP`
- `abbreviated_name`: `UTEP`
- `aka_name`: `<blank>`
- `schedule_id`: `UTEP`
- `2026_conference`: `Mountain West`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Sun Bowl`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `117`
- `board_committee_H`: `0.295677`
- `board_power_H`: `0.300377`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Mountain West`
- `source_fcs_reference`: `<blank>`

### 085 — Wyoming (`WYO`)

- `master_team_id`: `85`
- `name_id`: `team-085-wyoming`
- `team_name`: `Wyoming`
- `abbreviated_name`: `WYO`
- `aka_name`: `<blank>`
- `schedule_id`: `WYO`
- `2026_conference`: `Mountain West`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `War Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `95`
- `board_committee_H`: `0.361612`
- `board_power_H`: `0.354004`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Mountain West`
- `source_fcs_reference`: `<blank>`

### 086 — Army (`ARMY`)

- `master_team_id`: `86`
- `name_id`: `team-086-army`
- `team_name`: `Army`
- `abbreviated_name`: `ARMY`
- `aka_name`: `<blank>`
- `schedule_id`: `ARMY`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `American`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Michie Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `1`
- `conference_games`: `7`
- `board_rank_H`: `36`
- `board_committee_H`: `0.543694`
- `board_power_H`: `0.533713`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_continuity_inferred;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_8;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 087 — East Carolina (`ECU`)

- `master_team_id`: `87`
- `name_id`: `team-087-east-carolina`
- `team_name`: `East Carolina`
- `abbreviated_name`: `ECU`
- `aka_name`: `<blank>`
- `schedule_id`: `ECU`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `American`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Dowdy-Ficklen Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `45`
- `board_committee_H`: `0.486142`
- `board_power_H`: `0.482176`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_78;talent_pts_612;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 088 — Florida Atlantic (`FAU`)

- `master_team_id`: `88`
- `name_id`: `team-088-florida-atlantic`
- `team_name`: `Florida Atlantic`
- `abbreviated_name`: `FAU`
- `aka_name`: `<blank>`
- `schedule_id`: `FAU`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `American`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `FAU Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `73`
- `board_committee_H`: `0.418777`
- `board_power_H`: `0.422999`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;fau_source_typo_interpreted;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_82;talent_pts_605;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 089 — Louisiana Tech (`LT`)

- `master_team_id`: `89`
- `name_id`: `team-089-louisiana-tech`
- `team_name`: `Louisiana Tech`
- `abbreviated_name`: `LT`
- `aka_name`: `LaTech`
- `schedule_id`: `LT`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `Athletic`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Joe Aillet Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `100`
- `board_committee_H`: `0.353697`
- `board_power_H`: `0.342613`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 090 — Memphis (`MEM`)

- `master_team_id`: `90`
- `name_id`: `team-090-memphis`
- `team_name`: `Memphis`
- `abbreviated_name`: `MEM`
- `aka_name`: `<blank>`
- `schedule_id`: `MEM`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `Athletic`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Simmons Bank Liberty Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `69`
- `board_committee_H`: `0.423791`
- `board_power_H`: `0.404736`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_59;talent_pts_669;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 091 — Navy (`NAVY`)

- `master_team_id`: `91`
- `name_id`: `team-091-navy`
- `team_name`: `Navy`
- `abbreviated_name`: `NAVY`
- `aka_name`: `<blank>`
- `schedule_id`: `NAVY`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `American`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Navy-Marine Corps Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `2`
- `conference_games`: `7`
- `board_rank_H`: `30`
- `board_committee_H`: `0.560713`
- `board_power_H`: `0.559895`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_2;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 092 — New Mexico State (`NMSU`)

- `master_team_id`: `92`
- `name_id`: `team-092-new-mexico-state`
- `team_name`: `New Mexico State`
- `abbreviated_name`: `NMSU`
- `aka_name`: `<blank>`
- `schedule_id`: `NMSU`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `Athletic`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Aggie Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `97`
- `board_committee_H`: `0.355607`
- `board_power_H`: `0.36194`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 093 — North Texas (`UNT`)

- `master_team_id`: `93`
- `name_id`: `team-093-north-texas`
- `team_name`: `North Texas`
- `abbreviated_name`: `UNT`
- `aka_name`: `<blank>`
- `schedule_id`: `UNT`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `Athletic`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `DATCU Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `66`
- `board_committee_H`: `0.433553`
- `board_power_H`: `0.42906`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_0;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_96;talent_pts_569;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 094 — Rice (`RICE`)

- `master_team_id`: `94`
- `name_id`: `team-094-rice`
- `team_name`: `Rice`
- `abbreviated_name`: `RICE`
- `aka_name`: `<blank>`
- `schedule_id`: `RICE`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `Athletic`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Rice Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `110`
- `board_committee_H`: `0.322883`
- `board_power_H`: `0.323145`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 095 — South Florida (`USF`)

- `master_team_id`: `95`
- `name_id`: `team-095-south-florida`
- `team_name`: `South Florida`
- `abbreviated_name`: `USF`
- `aka_name`: `<blank>`
- `schedule_id`: `USF`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `American`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Raymond James Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `8`
- `away_listed_games`: `4`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `76`
- `board_committee_H`: `0.414807`
- `board_power_H`: `0.383969`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_61;talent_pts_667;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 096 — Southern Miss (`USM`)

- `master_team_id`: `96`
- `name_id`: `team-096-southern-miss`
- `team_name`: `Southern Miss`
- `abbreviated_name`: `USM`
- `aka_name`: `<blank>`
- `schedule_id`: `USM`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `American`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `M.M. Roberts Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `116`
- `board_committee_H`: `0.296365`
- `board_power_H`: `0.29084`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_83;talent_pts_603;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 097 — Temple (`TEM`)

- `master_team_id`: `97`
- `name_id`: `team-097-temple`
- `team_name`: `Temple`
- `abbreviated_name`: `TEM`
- `aka_name`: `<blank>`
- `schedule_id`: `TEM`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `American`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Lincoln Financial Field`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `59`
- `board_committee_H`: `0.452156`
- `board_power_H`: `0.451937`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_7;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 098 — Tulane (`TLN`)

- `master_team_id`: `98`
- `name_id`: `team-098-tulane`
- `team_name`: `Tulane`
- `abbreviated_name`: `TLN`
- `aka_name`: `<blank>`
- `schedule_id`: `TLN`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `Athletic`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Yulman Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `32`
- `board_committee_H`: `0.558163`
- `board_power_H`: `0.548755`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_68;talent_pts_651;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 099 — Tulsa (`TLSA`)

- `master_team_id`: `99`
- `name_id`: `team-099-tulsa`
- `team_name`: `Tulsa`
- `abbreviated_name`: `TLSA`
- `aka_name`: `<blank>`
- `schedule_id`: `TLSA`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `Athletic`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `H.A. Chapman Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `75`
- `board_committee_H`: `0.414894`
- `board_power_H`: `0.415538`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_85;talent_pts_595;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 100 — UAB (`UAB`)

- `master_team_id`: `100`
- `name_id`: `team-100-uab`
- `team_name`: `UAB`
- `abbreviated_name`: `UAB`
- `aka_name`: `<blank>`
- `schedule_id`: `UAB`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `American`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Protective Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `112`
- `board_committee_H`: `0.308085`
- `board_power_H`: `0.31182`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 101 — UTSA (`UTSA`)

- `master_team_id`: `101`
- `name_id`: `team-101-utsa`
- `team_name`: `UTSA`
- `abbreviated_name`: `UTSA`
- `aka_name`: `Texas-San Antonio`
- `schedule_id`: `UTSA`
- `2026_conference`: `American`
- `2026_division`: `FBS`
- `2026_conference_division`: `Athletic`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Alamodome`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `8`
- `board_rank_H`: `85`
- `board_committee_H`: `0.384475`
- `board_power_H`: `0.368912`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_5;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_65;talent_pts_662;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `American`
- `source_fcs_reference`: `<blank>`

### 102 — Buffalo (`BUFF`)

- `master_team_id`: `102`
- `name_id`: `team-102-buffalo`
- `team_name`: `Buffalo`
- `abbreviated_name`: `BUFF`
- `aka_name`: `<blank>`
- `schedule_id`: `BUFF`
- `2026_conference`: `Atlantic-8`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `UB Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `96`
- `board_committee_H`: `0.359159`
- `board_power_H`: `0.353984`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Atlantic-8`
- `source_fcs_reference`: `<blank>`

### 103 — Coastal Carolina (`CCU`)

- `master_team_id`: `103`
- `name_id`: `team-103-coastal-carolina`
- `team_name`: `Coastal Carolina`
- `abbreviated_name`: `CCU`
- `aka_name`: `<blank>`
- `schedule_id`: `CCU`
- `2026_conference`: `Atlantic-8`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Brooks Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `121`
- `board_committee_H`: `0.276234`
- `board_power_H`: `0.265155`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_80;talent_pts_611;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Atlantic-8`
- `source_fcs_reference`: `<blank>`

### 104 — Delaware (`DEL`)

- `master_team_id`: `104`
- `name_id`: `team-104-delaware`
- `team_name`: `Delaware`
- `abbreviated_name`: `DEL`
- `aka_name`: `<blank>`
- `schedule_id`: `DEL`
- `2026_conference`: `Atlantic-8`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Delaware Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `4`
- `away_listed_games`: `8`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `102`
- `board_committee_H`: `0.351383`
- `board_power_H`: `0.346718`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_7;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Atlantic-8`
- `source_fcs_reference`: `<blank>`

### 105 — Florida International (`FIU`)

- `master_team_id`: `105`
- `name_id`: `team-105-florida-international`
- `team_name`: `Florida International`
- `abbreviated_name`: `FIU`
- `aka_name`: `<blank>`
- `schedule_id`: `FIU`
- `2026_conference`: `Atlantic-8`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Pitbull Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `103`
- `board_committee_H`: `0.349569`
- `board_power_H`: `0.338874`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_continuity_inferred;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_2;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_98;talent_pts_563;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Atlantic-8`
- `source_fcs_reference`: `<blank>`

### 106 — Georgia Southern (`GASO`)

- `master_team_id`: `106`
- `name_id`: `team-106-georgia-southern`
- `team_name`: `Georgia Southern`
- `abbreviated_name`: `GASO`
- `aka_name`: `<blank>`
- `schedule_id`: `GASO`
- `2026_conference`: `Atlantic-8`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Paulson Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `113`
- `board_committee_H`: `0.303954`
- `board_power_H`: `0.297686`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_93;talent_pts_574;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Atlantic-8`
- `source_fcs_reference`: `<blank>`

### 107 — Georgia State (`GAST`)

- `master_team_id`: `107`
- `name_id`: `team-107-georgia-state`
- `team_name`: `Georgia State`
- `abbreviated_name`: `GAST`
- `aka_name`: `Georgia St.`
- `schedule_id`: `GAST`
- `2026_conference`: `Atlantic-8`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Center Parc Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `13`
- `home_listed_games`: `6`
- `away_listed_games`: `7`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `99`
- `board_committee_H`: `0.354181`
- `board_power_H`: `0.348462`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_3;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_77;talent_pts_612;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `schedule_count_review:13`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Atlantic-8`
- `source_fcs_reference`: `<blank>`

### 108 — Marshall (`MRSH`)

- `master_team_id`: `108`
- `name_id`: `team-108-marshall`
- `team_name`: `Marshall`
- `abbreviated_name`: `MRSH`
- `aka_name`: `<blank>`
- `schedule_id`: `MRSH`
- `2026_conference`: `Atlantic-8`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Joan C. Edwards Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `74`
- `board_committee_H`: `0.416791`
- `board_power_H`: `0.403561`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_continuity_inferred;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_6;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_89;talent_pts_591;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Atlantic-8`
- `source_fcs_reference`: `<blank>`

### 109 — Middle Tennessee (`MTSU`)

- `master_team_id`: `109`
- `name_id`: `team-109-middle-tennessee`
- `team_name`: `Middle Tennessee`
- `abbreviated_name`: `MTSU`
- `aka_name`: `Middle Tennessee St.`
- `schedule_id`: `MTSU`
- `2026_conference`: `Atlantic-8`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Floyd Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `114`
- `board_committee_H`: `0.302305`
- `board_power_H`: `0.304647`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_origin_unverified;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Atlantic-8`
- `source_fcs_reference`: `<blank>`

### 110 — Old Dominion (`ODU`)

- `master_team_id`: `110`
- `name_id`: `team-110-old-dominion`
- `team_name`: `Old Dominion`
- `abbreviated_name`: `ODU`
- `aka_name`: `<blank>`
- `schedule_id`: `ODU`
- `2026_conference`: `Atlantic-8`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `S.B. Ballard Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `60`
- `board_committee_H`: `0.451843`
- `board_power_H`: `0.431662`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_unsourced_outside_top100;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_tail_unreachable_247_pagination;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Atlantic-8`
- `source_fcs_reference`: `<blank>`

### 111 — Troy (`TROY`)

- `master_team_id`: `111`
- `name_id`: `team-111-troy`
- `team_name`: `Troy`
- `abbreviated_name`: `TROY`
- `aka_name`: `<blank>`
- `schedule_id`: `TROY`
- `2026_conference`: `Atlantic-8`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Veterans Memorial Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `0`
- `conference_games`: `9`
- `board_rank_H`: `105`
- `board_committee_H`: `0.343831`
- `board_power_H`: `0.328215`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_continuity_inferred;returning_qb_confirmed;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_4;ol_starts_unavailable;draft_2026_final;draft_picks_0;draft_count_mapped;portal_outside_top50;portal_proxy_rp_derived;talent_247_composite_sourced;talent_rank_99;talent_pts_562;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;portal_proxy_retained_user_ruling_2026_07_08;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Atlantic-8`
- `source_fcs_reference`: `<blank>`

### 112 — Colgate (`COLG`)

- `master_team_id`: `112`
- `name_id`: `team-112-colgate`
- `team_name`: `Colgate`
- `abbreviated_name`: `COLG`
- `aka_name`: `<blank>`
- `schedule_id`: `COLG`
- `2026_conference`: `ECL`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Andy Kerr Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `7`
- `board_rank_H`: `109`
- `board_committee_H`: `0.325377`
- `board_power_H`: `0.325377`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;ecl_fcs_scaled;hc_continuity_inferred;oc_unknown;dc_unknown;qb_unresolved;returning_production_unavailable;market_data_unavailable;ecl_2025_continuity_baseline;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_unavailable;ol_starts_unavailable;user_directed_ecl_scaling;ecl_rank_order_user_defined;draft_2026_final;draft_picks_0;draft_count_mapped;ecl_no_draft_losses;portal_data_unavailable_fcs;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ECL`
- `source_fcs_reference`: `<blank>`

### 113 — Cornell (`COR`)

- `master_team_id`: `113`
- `name_id`: `team-113-cornell`
- `team_name`: `Cornell`
- `abbreviated_name`: `COR`
- `aka_name`: `<blank>`
- `schedule_id`: `COR`
- `2026_conference`: `ECL`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Schoellkopf Field`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `7`
- `board_rank_H`: `111`
- `board_committee_H`: `0.310004`
- `board_power_H`: `0.310004`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;ecl_fcs_scaled;hc_continuity_inferred;oc_unknown;dc_unknown;qb_unresolved;returning_production_unavailable;market_data_unavailable;ecl_2025_continuity_baseline;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_unavailable;ol_starts_unavailable;user_directed_ecl_scaling;ecl_rank_order_user_defined;draft_2026_final;draft_picks_0;draft_count_mapped;ecl_no_draft_losses;portal_data_unavailable_fcs;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ECL`
- `source_fcs_reference`: `<blank>`

### 114 — Harvard (`HARV`)

- `master_team_id`: `114`
- `name_id`: `team-114-harvard`
- `team_name`: `Harvard`
- `abbreviated_name`: `HARV`
- `aka_name`: `<blank>`
- `schedule_id`: `HARV`
- `2026_conference`: `ECL`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Harvard Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `7`
- `board_rank_H`: `118`
- `board_committee_H`: `0.291647`
- `board_power_H`: `0.291647`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;ecl_fcs_scaled;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_unavailable;market_data_unavailable;qb_departure_confirmed_successor_unknown;ecl_2025_continuity_baseline;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_unavailable;ol_starts_unavailable;user_directed_ecl_scaling;ecl_rank_order_user_defined;draft_2026_final;draft_picks_0;draft_count_mapped;ecl_no_draft_losses;portal_data_unavailable_fcs;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ECL`
- `source_fcs_reference`: `<blank>`

### 115 — Holy Cross (`HC`)

- `master_team_id`: `115`
- `name_id`: `team-115-holy-cross`
- `team_name`: `Holy Cross`
- `abbreviated_name`: `HC`
- `aka_name`: `<blank>`
- `schedule_id`: `HC`
- `2026_conference`: `ECL`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Fitton Field`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `7`
- `board_rank_H`: `94`
- `board_committee_H`: `0.363442`
- `board_power_H`: `0.363442`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;ecl_fcs_scaled;hc_continuity_inferred;oc_unknown;dc_unknown;qb_unresolved;returning_production_unavailable;market_data_unavailable;ecl_2025_continuity_baseline;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_unavailable;ol_starts_unavailable;user_directed_ecl_scaling;ecl_rank_order_user_defined;draft_2026_final;draft_picks_0;draft_count_mapped;ecl_no_draft_losses;portal_data_unavailable_fcs;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ECL`
- `source_fcs_reference`: `<blank>`

### 116 — Lehigh (`LEH`)

- `master_team_id`: `116`
- `name_id`: `team-116-lehigh`
- `team_name`: `Lehigh`
- `abbreviated_name`: `LEH`
- `aka_name`: `<blank>`
- `schedule_id`: `LEH`
- `2026_conference`: `ECL`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Goodman Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `7`
- `board_rank_H`: `27`
- `board_committee_H`: `0.593009`
- `board_power_H`: `0.593009`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;ecl_fcs_scaled;hc_continuity_inferred;oc_unknown;dc_unknown;qb_unresolved;returning_production_unavailable;market_data_unavailable;ecl_2025_continuity_baseline;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_unavailable;ol_starts_unavailable;user_directed_ecl_scaling;ecl_rank_order_user_defined;draft_2026_final;draft_picks_0;draft_count_mapped;ecl_no_draft_losses;portal_data_unavailable_fcs;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ECL`
- `source_fcs_reference`: `<blank>`

### 117 — Penn (`PENN`)

- `master_team_id`: `117`
- `name_id`: `team-117-penn`
- `team_name`: `Penn`
- `abbreviated_name`: `PENN`
- `aka_name`: `<blank>`
- `schedule_id`: `PENN`
- `2026_conference`: `ECL`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Franklin Field`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `7`
- `board_rank_H`: `104`
- `board_committee_H`: `0.344614`
- `board_power_H`: `0.344614`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;ecl_fcs_scaled;source_confirmed_staff;oc_unknown;dc_unknown;qb_unresolved;returning_production_unavailable;market_data_unavailable;ecl_2025_continuity_baseline;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_unavailable;ol_starts_unavailable;user_directed_ecl_scaling;ecl_rank_order_user_defined;draft_2026_final;draft_picks_0;draft_count_mapped;ecl_no_draft_losses;portal_data_unavailable_fcs;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ECL`
- `source_fcs_reference`: `<blank>`

### 118 — Princeton (`PRIN`)

- `master_team_id`: `118`
- `name_id`: `team-118-princeton`
- `team_name`: `Princeton`
- `abbreviated_name`: `PRIN`
- `aka_name`: `<blank>`
- `schedule_id`: `PRIN`
- `2026_conference`: `ECL`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Powers Field at Princeton Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `7`
- `board_rank_H`: `78`
- `board_committee_H`: `0.405528`
- `board_power_H`: `0.405528`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;ecl_fcs_scaled;hc_continuity_inferred;oc_unknown;dc_unknown;returning_production_unavailable;market_data_unavailable;qb_departure_confirmed_successor_unknown;ecl_2025_continuity_baseline;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_unavailable;ol_starts_unavailable;user_directed_ecl_scaling;ecl_rank_order_user_defined;draft_2026_final;draft_picks_0;draft_count_mapped;ecl_no_draft_losses;portal_data_unavailable_fcs;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ECL`
- `source_fcs_reference`: `<blank>`

### 119 — Yale (`YALE`)

- `master_team_id`: `119`
- `name_id`: `team-119-yale`
- `team_name`: `Yale`
- `abbreviated_name`: `YALE`
- `aka_name`: `<blank>`
- `schedule_id`: `YALE`
- `2026_conference`: `ECL`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `1`
- `independent_flag`: `0`
- `stadium`: `Yale Bowl`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `5`
- `away_listed_games`: `7`
- `neutral_site_games`: `0`
- `conference_games`: `7`
- `board_rank_H`: `119`
- `board_committee_H`: `0.281804`
- `board_power_H`: `0.281804`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;synthetic_conference_rule_applied;ecl_fcs_scaled;hc_continuity_inferred;oc_unknown;dc_unknown;qb_unresolved;returning_production_unavailable;market_data_unavailable;ecl_2025_continuity_baseline;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_unavailable;ol_starts_unavailable;user_directed_ecl_scaling;ecl_rank_order_user_defined;draft_2026_final;draft_picks_0;draft_count_mapped;ecl_no_draft_losses;portal_data_unavailable_fcs;stadium_unsourced_model_knowledge;review_tier_hard;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `ECL`
- `source_fcs_reference`: `<blank>`

### 120 — Notre Dame (`ND`)

- `master_team_id`: `120`
- `name_id`: `team-120-notre-dame`
- `team_name`: `Notre Dame`
- `abbreviated_name`: `ND`
- `aka_name`: `<blank>`
- `schedule_id`: `ND`
- `2026_conference`: `Independent`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `1`
- `stadium`: `Notre Dame Stadium`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `7`
- `away_listed_games`: `5`
- `neutral_site_games`: `2`
- `conference_games`: `0`
- `board_rank_H`: `9`
- `board_committee_H`: `0.746688`
- `board_power_H`: `0.726512`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;returning_qb_confirmed;returning_production_espn_sourced;market_review_required;oc_continuity_inferred;dc_continuity_inferred;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_7;draft_2026_final;draft_picks_6;draft_count_mapped;portal_247_rank_11;portal_rank_mapped;talent_247_composite_sourced;talent_rank_9;talent_pts_912;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Independent`
- `source_fcs_reference`: `<blank>`

### 121 — UConn (`UConn`)

- `master_team_id`: `121`
- `name_id`: `team-121-uconn`
- `team_name`: `UConn`
- `abbreviated_name`: `UConn`
- `aka_name`: `<blank>`
- `schedule_id`: `UConn`
- `2026_conference`: `Independent`
- `2026_division`: `FBS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `1`
- `stadium`: `Pratt & Whitney Stadium at Rentschler Field`
- `home_field_advantage_modifier`: `1`
- `regular_season_games`: `12`
- `home_listed_games`: `6`
- `away_listed_games`: `6`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `71`
- `board_committee_H`: `0.42101`
- `board_power_H`: `0.414855`
- `championship_eligible`: `Y`
- `identity_validation_status`: `MATCHED_MASTER_SCHEDULE`
- `schedule_validation_status`: `MATCHED_V5`
- `board_validation_status`: `MATCHED_IH_V2`
- `source_team_master`: `Pre-season2026 FBS Team Master.xlsx`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `2026 Board I-H v2.xlsx`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `conference_alignment_preserved;source_confirmed_staff;oc_unknown;dc_unknown;returning_production_espn_sourced;qb_projection_athlon_sourced;market_review_required;market_asof_2026_07_01;ap_field_repurposed_ncp_synthetic;ncp_pending_user_input;def_starters_athlon_sourced;ret_off_starters_1;ol_starts_unavailable;draft_2026_final;draft_picks_1;draft_count_mapped;portal_outside_top50;portal_outgoing_adjust_sourced;talent_247_composite_sourced;talent_rank_97;talent_pts_568;talent_year_2025_baseline;talent_2026_not_published;stadium_unsourced_model_knowledge;review_tier_soft_market_poll_only;manual_review;talent_transform_rank_anchored_user_ruling;off_starters_column_authorized;hfa_baseline_3p5_locked;hfa_modifier_league_average`
- `notes`: `<blank>`
- `entity_scope`: `FBS_MEMBER`
- `schedule_conference_label`: `Independent`
- `source_fcs_reference`: `<blank>`

### 122 — Arkansas State (`ARST`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Arkansas State`
- `abbreviated_name`: `ARST`
- `aka_name`: `Arkansas St.`
- `schedule_id`: `ARST`
- `2026_conference`: `<blank>`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `1`
- `home_listed_games`: `0`
- `away_listed_games`: `1`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced. Exact 2026 FCS conference not available; left blank.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `<blank>`

### 123 — Charlotte (`CHAR`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Charlotte`
- `abbreviated_name`: `CHAR`
- `aka_name`: `<blank>`
- `schedule_id`: `CHAR`
- `2026_conference`: `<blank>`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `1`
- `home_listed_games`: `0`
- `away_listed_games`: `1`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced. Exact 2026 FCS conference not available; left blank.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `<blank>`

### 124 — Cal Poly (`CP`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Cal Poly`
- `abbreviated_name`: `CP`
- `aka_name`: `<blank>`
- `schedule_id`: `CP`
- `2026_conference`: `Big Sky`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `1`
- `home_listed_games`: `0`
- `away_listed_games`: `1`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Project FCS: CFB26`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `Project FCS: CFB26`

### 125 — Duquesne (`DUQ`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Duquesne`
- `abbreviated_name`: `DUQ`
- `aka_name`: `<blank>`
- `schedule_id`: `DUQ`
- `2026_conference`: `NEC`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `1`
- `home_listed_games`: `0`
- `away_listed_games`: `1`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Project FCS: CFB26`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `Project FCS: CFB26`

### 126 — Eastern Michigan (`EMU`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Eastern Michigan`
- `abbreviated_name`: `EMU`
- `aka_name`: `<blank>`
- `schedule_id`: `EMU`
- `2026_conference`: `<blank>`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `1`
- `home_listed_games`: `1`
- `away_listed_games`: `0`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced. Exact 2026 FCS conference not available; left blank.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `<blank>`

### 127 — Idaho (`IDHO`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Idaho`
- `abbreviated_name`: `IDHO`
- `aka_name`: `<blank>`
- `schedule_id`: `IDHO`
- `2026_conference`: `Big Sky`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `2`
- `home_listed_games`: `0`
- `away_listed_games`: `2`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Canonical Season Registry.xlsx; Project FCS: CFB26`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `Canonical Season Registry.xlsx; Project FCS: CFB26`

### 128 — Sacramento State (`SAC`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Sacramento State`
- `abbreviated_name`: `SAC`
- `aka_name`: `<blank>`
- `schedule_id`: `SAC`
- `2026_conference`: `Big Sky`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `2`
- `home_listed_games`: `0`
- `away_listed_games`: `2`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Canonical Season Registry.xlsx; Project FCS: CFB26`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `Canonical Season Registry.xlsx; Project FCS: CFB26`

### 129 — Southern Utah (`SUU`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Southern Utah`
- `abbreviated_name`: `SUU`
- `aka_name`: `<blank>`
- `schedule_id`: `SUU`
- `2026_conference`: `UAC`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `1`
- `home_listed_games`: `0`
- `away_listed_games`: `1`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Project FCS: CFB26`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `Project FCS: CFB26`

### 130 — Toledo (`TOL`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Toledo`
- `abbreviated_name`: `TOL`
- `aka_name`: `<blank>`
- `schedule_id`: `TOL`
- `2026_conference`: `<blank>`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `1`
- `home_listed_games`: `1`
- `away_listed_games`: `0`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced. Exact 2026 FCS conference not available; left blank.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `<blank>`

### 131 — Louisiana (UL Lafayette) (`ULL`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Louisiana (UL Lafayette)`
- `abbreviated_name`: `ULL`
- `aka_name`: `<blank>`
- `schedule_id`: `ULL`
- `2026_conference`: `<blank>`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `1`
- `home_listed_games`: `0`
- `away_listed_games`: `1`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced. Exact 2026 FCS conference not available; left blank.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `<blank>`

### 132 — Louisiana-Monroe (`ULM`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Louisiana-Monroe`
- `abbreviated_name`: `ULM`
- `aka_name`: `<blank>`
- `schedule_id`: `ULM`
- `2026_conference`: `<blank>`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `1`
- `home_listed_games`: `0`
- `away_listed_games`: `1`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced. Exact 2026 FCS conference not available; left blank.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `<blank>`

### 133 — Western Kentucky (`WKU`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Western Kentucky`
- `abbreviated_name`: `WKU`
- `aka_name`: `<blank>`
- `schedule_id`: `WKU`
- `2026_conference`: `<blank>`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `1`
- `home_listed_games`: `0`
- `away_listed_games`: `1`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced. Exact 2026 FCS conference not available; left blank.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `<blank>`

### 134 — Western Michigan (`WMU`)

- `master_team_id`: `<blank>`
- `name_id`: `<blank>`
- `team_name`: `Western Michigan`
- `abbreviated_name`: `WMU`
- `aka_name`: `<blank>`
- `schedule_id`: `WMU`
- `2026_conference`: `<blank>`
- `2026_division`: `FCS`
- `2026_conference_division`: `<blank>`
- `power_conference_flag`: `0`
- `g5_flag`: `0`
- `independent_flag`: `<blank>`
- `stadium`: `<blank>`
- `home_field_advantage_modifier`: `<blank>`
- `regular_season_games`: `1`
- `home_listed_games`: `1`
- `away_listed_games`: `0`
- `neutral_site_games`: `0`
- `conference_games`: `0`
- `board_rank_H`: `<blank>`
- `board_committee_H`: `<blank>`
- `board_power_H`: `<blank>`
- `championship_eligible`: `<blank>`
- `identity_validation_status`: `MATCHED_SCHEDULE_AND_NAMED_SOURCE`
- `schedule_validation_status`: `MATCHED_V5_FCS`
- `board_validation_status`: `NOT_APPLICABLE_FCS`
- `source_team_master`: `<blank>`
- `source_schedule`: `2026_FBS_Schedule_LOCKED_v5.xlsx`
- `source_board`: `<blank>`
- `source_registry`: `Canonical Season Registry.xlsx`
- `provenance_codes`: `schedule_v5_fcs_opponent;no_master_numeric_id_available;no_name_id_available`
- `notes`: `Schedule-only FCS opponent. Numeric master_team_id and name_id intentionally blank because no authoritative values were surfaced. Exact 2026 FCS conference not available; left blank.`
- `entity_scope`: `SCHEDULE_ONLY_FCS`
- `schedule_conference_label`: `FCS`
- `source_fcs_reference`: `<blank>`

## Validation Checklist

- [x] Source CSV SHA-256 matches the supplied manifest.
- [x] 134 total records emitted.
- [x] 121 records have `entity_scope = FBS_MEMBER`.
- [x] 13 records have `entity_scope = SCHEDULE_ONLY_FCS`.
- [x] 134 unique `schedule_id` values emitted.
- [x] All 35 CSV columns retained in every full record.
- [x] Empty source values rendered as `<blank>` rather than inferred.
- [x] All 13 schedule-only FCS records retain blank `master_team_id` and `name_id`.

## Model Response Rule

When answering a question that depends on this universe, cite or reproduce the canonical value from the matching record. If the requested fact is `<blank>` or the team is absent, say that the canonical master does not provide it and return `BLOCKED` for any action that requires the missing value. Do not repair the gap with external knowledge unless a separately governed source is explicitly provided and authorized to supersede this artifact.
