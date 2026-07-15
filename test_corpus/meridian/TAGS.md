# Meridian corpus — tags and ingestion

Suggested tags per document, and ready-to-run ingest commands. Tags echo the
assignment's examples (`compliance`, `onboarding`, `product`, `hr`) plus the
topic areas this corpus actually has. Several documents carry two tags on
purpose — that's what makes `search_by_tag`'s `tag_match="any"|"all"` testable.

**Never ingest `COMPANY.md`** — it holds the negative-control facts.

| Document | Tags | Why |
|---|---|---|
| `kestrel-settlement-policy.md` | `settlement, compliance` | The rail's governing policy — both an ops and a compliance artifact |
| `meridian-aml-policy.md` | `compliance` | Client-tier AML rules |
| `meridian-sanctions-screening-standard.pdf` | `compliance` | Osprey list, SCR rules — pure compliance |
| `meridian-hr-handbook.md` | `hr` | Vacation, onboarding of employees |
| `meridian-remote-work-policy.md` | `hr` | Hybrid rules, stipends, Perch VPN |
| `kestrel-participant-onboarding-guide.pdf` | `onboarding, settlement` | Institution onboarding onto the rail |
| `meridian-product-catalog.pdf` | `product` | Commercial terms for all six products |
| `kestrel-api-changelog.md` | `product, settlement` | API surface of the settlement product |
| `meridian-business-continuity-plan.pdf` | `operations, settlement` | Severities, RTO/RPO, failover |
| `meridian-faq-export.txt` | `faq` | Cross-topic Q/A export |
| `meridian-glossary.txt` | `reference` | Terms and codes across every domain |

Tag census after full ingest: `settlement` (4), `compliance` (3), `hr` (2),
`product` (2), `onboarding` (1), `operations` (1), `faq` (1), `reference` (1).

## Ingest commands

From the repo root, stack running (`docker compose up`), `UI_PASSWORD` set:

```bash
D=test_corpus/meridian/docs
U="admin:$UI_PASSWORD"
API=http://localhost:8000/api/documents

curl -u $U -F "file=@$D/kestrel-settlement-policy.md"                 -F "tags=settlement,compliance" -X POST $API
curl -u $U -F "file=@$D/meridian-aml-policy.md"                       -F "tags=compliance"            -X POST $API
curl -u $U -F "file=@$D/meridian-sanctions-screening-standard.pdf"    -F "tags=compliance"            -X POST $API
curl -u $U -F "file=@$D/meridian-hr-handbook.md"                      -F "tags=hr"                    -X POST $API
curl -u $U -F "file=@$D/meridian-remote-work-policy.md"               -F "tags=hr"                    -X POST $API
curl -u $U -F "file=@$D/kestrel-participant-onboarding-guide.pdf"     -F "tags=onboarding,settlement" -X POST $API
curl -u $U -F "file=@$D/meridian-product-catalog.pdf"                 -F "tags=product"               -X POST $API
curl -u $U -F "file=@$D/kestrel-api-changelog.md"                     -F "tags=product,settlement"    -X POST $API
curl -u $U -F "file=@$D/meridian-business-continuity-plan.pdf"        -F "tags=operations,settlement" -X POST $API
curl -u $U -F "file=@$D/meridian-faq-export.txt"                      -F "tags=faq"                   -X POST $API
curl -u $U -F "file=@$D/meridian-glossary.txt"                        -F "tags=reference"             -X POST $API
```

Every response should report `"outcome": "created"` (or `"unchanged"` on
re-runs) and a positive chunk count. Verify with:

```bash
curl -s -u $U http://localhost:8000/api/documents | python -m json.tool
```
