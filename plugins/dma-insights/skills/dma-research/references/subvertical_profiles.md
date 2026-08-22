# Subvertical Profiles & Classification

Read this file during Batch 1 Step 3 (regulatory search / classification) and Batch 2
Step 2 (classification decision tree).

---

## Classification Decision Tree

Apply in order. First match wins.

1. NCUA regulated? → **Credit Unions (SV2)**
2. OCC/FDIC/Fed bank? → Determine model:
   - Retail/SMB dominant → **Regional Banks (SV1)**
   - Commercial dominant → **Commercial Lending (SV3)**
   - Capital markets/trading → **CIB (SV4)**
3. SEC Form ADV registered? →
   - Client-facing advisory → **RIAs & Broker-Dealers (SV5)**
   - Fund management → **Asset Management (SV6)**
4. FINRA registered BD? → **RIAs & Broker-Dealers (SV5)**
5. State DOI licensed? →
   - Underwriting risk → **Insurance Carriers (SV8)**
   - Distribution only → **Insurance Brokers (SV7)**
6. None of the above → **Escalate for manual classification**

### Disambiguation Rules
- **Multi-licensed**: Classify by dominant revenue (>50%). If balanced, recommend separate assessments.
- **HoldCo vs OpCo**: HoldCo = classify by dominant subsidiary. OpCo = classify by that entity's license. Platform = build Regulatory Coverage Map.
- **Canada**: OSFI → Regional Banks or CIB. Provincial securities → RIAs or Asset Mgmt. Provincial insurance → Carriers/Brokers. FSRA → Credit Unions.

### Confidence Scoring (max 100)

| Component | Max Points | Criteria |
|-----------|-----------|---------|
| Regulatory Anchor | 40 | T1 evidence of primary regulator |
| Operating Model | 30 | T1/T2 evidence of business activities |
| Revenue Engine | 20 | T1/T2 evidence of primary revenue sources |
| Boundary Clarity | 10 | Entity boundary resolved, no contradictions |

**Deductions**: Parent HoldCo without direct license (-10), Single-source key anchor (-10),
Unresolved boundary (-10), Contradictory evidence unresolved (-15)

---

## Subvertical Profiles

### SV1: Regional Banks ($1B-$100B)
**Regulators**: OCC, FDIC, Fed, State DOB
**T1 Sources**: KB-US-002 (FDIC Call Reports), KB-US-003 (OCC Enforcement), Fed actions, State banking records
**Financial Metrics**: Total assets, deposits, loans, NIM, efficiency ratio, NPL ratio
**Regulatory URLs**: FDIC BankFind (`banks.data.fdic.gov`), OCC Bank Search, FFIEC NPW
**Size tiers**: Medium ($2B-$10B), Large ($10B-$50B), Mega (>$50B)

### SV2: Credit Unions ($100M-$50B+)
**Regulators**: NCUA, State CU regulators
**T1 Sources**: KB-US-001 (NCUA Call Reports), KB-US-004 (NCUA Enforcement), State CU exams, CUSO registrations
**Financial Metrics**: Total assets, shares, loans, net worth ratio, ROA, member count
**Regulatory URLs**: NCUA Research (`mapping.ncua.gov`), NCUA Enforcement
**Size tiers**: Nano (<$100M), Micro ($100M-$500M), Small ($500M-$2B), Medium ($2B-$10B), Large ($10B-$50B)

### SV3: Commercial Lending
**Regulators**: OCC/FDIC, State lender licenses
**T1 Sources**: Bank regulator filings, SBA lender registrations, State licensing
**Financial Metrics**: Loan portfolio, CRE concentration, C&I volume, NPA ratio

### SV4: CIB (Capital Markets)
**Regulators**: SEC, FINRA, Fed, CFTC
**T1 Sources**: SEC EDGAR, Fed SR letters, FINRA BrokerCheck, CFTC registrations
**Financial Metrics**: Revenue by segment, trading revenue, IB fees, AUM

### SV5: RIAs & Broker-Dealers
**Regulators**: SEC, FINRA, State securities
**T1 Sources**: SEC Form ADV, FINRA BrokerCheck, State securities, SEC enforcement
**Financial Metrics**: AUM, client count, revenue, advisor count
**Regulatory URLs**: SEC IAPD (`adviserinfo.sec.gov`), FINRA BrokerCheck (`brokercheck.finra.org`)

### SV6: Asset Management
**Regulators**: SEC, CFTC
**T1 Sources**: Form ADV, Form N-1A, 13F filings, SEC enforcement
**Financial Metrics**: AUM by strategy, fund performance, net flows, expense ratios

### SV7: Insurance Brokers
**Regulators**: State DOIs, NAIC
**T1 Sources**: State DOI licenses, NAIC producer database
**Financial Metrics**: Premium placed, commission revenue, producer count, acquisitions

### SV8: Insurance Carriers
**Regulators**: State DOIs, NAIC, OSFI (Canada)
**T1 Sources**: State statutory filings, AM Best, NAIC annual statements, Market conduct exams
**Financial Metrics**: DWP, combined ratio, loss ratio, investment income, surplus

---

## Size Tiers & Adjustment

| Tier | Range | Context Adjustment |
|------|-------|--------------------|
| Nano | <$100M | -1.0 (limited resources, outsourced most tech) |
| Micro | $100M-$500M | -0.8 |
| Small | $500M-$2B | -0.6 |
| Medium | $2B-$10B | -0.4 |
| Large | $10B-$50B | -0.2 |
| Mega | >$50B | 0 (full capability expected) |

---

## Regulatory URL Quick Reference

### Credit Unions
- NCUA Research: `https://mapping.ncua.gov/ResearchCreditUnion`
- NCUA Enforcement: `https://www.ncua.gov/regulation-supervision/enforcement-actions`

### Banks
- FDIC BankFind: `https://banks.data.fdic.gov/bankfind-suite/bankfind`
- OCC Bank Search: `https://www.occ.gov/topics/charters-and-licensing/financial-institution-lists/`
- Fed Structure: `https://www.ffiec.gov/NPW`
- OCC Enforcement: `https://www.occ.gov/topics/laws-and-regulations/enforcement-actions/`

### Securities
- SEC IAPD: `https://adviserinfo.sec.gov/`
- FINRA BrokerCheck: `https://brokercheck.finra.org/`
- SEC EDGAR: `https://www.sec.gov/cgi-bin/browse-edgar`
- SEC Enforcement: `https://www.sec.gov/divisions/enforce/enforceactions.shtml`

### Insurance
- NAIC Company: `https://content.naic.org/cis_consumer_information.htm`
- AM Best: `https://web.ambest.com/ratings-services/find-best-ratings`

### Cross-Sector
- CFPB Complaints: `https://www.consumerfinance.gov/data-research/consumer-complaints/`
- CFPB Enforcement: `https://www.consumerfinance.gov/enforcement/actions/`
