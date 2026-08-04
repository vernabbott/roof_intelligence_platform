# Production Baseline

- Baseline ID: `production-2026-08-04.2`
- Component: PilotPoint IQ Roof Intelligence
- Included application source: all Roof Intelligence changes through commit `9d8fc00`
- Paired PCS source: all PCS Proposal Management changes through commit `d61d1a2`
- Deployment: Python report worker and reference library invoked by PCS through `ROOF_INTELLIGENCE_PROJECT_DIR`
- Desktop host: `/Applications/PCS_Proposal.app`

This paired baseline is the production rollback point created before beta and
multi-tenant development begins. Production releases should be built from the
matching `production-2026-08-04.2` tag in both repositories.
