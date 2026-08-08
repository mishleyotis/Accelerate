# Language: opportunity framing

Everything on a client dashboard is read by, or in front of, the client. A gap stated as a
deficiency invites defensiveness; the same gap stated as available value invites a
conversation. This is not softening — the finding is identical and the evidence is unchanged.
What differs is whether the sentence is about what the institution failed to do or about what
is now available to it.

## The test

Read the sentence aloud as though the client's Chief Information Officer is in the room,
because they will be. Three questions:

1. **Does it assign fault?** "Failed to", "neglected", "should have" — the assessment does not
   adjudicate past decisions.
2. **Does it describe a person or a team?** Capability sits with institutions, not
   individuals. "The team lacks" is both accusatory and unfalsifiable.
3. **Would you say it this way to their face?** If the answer is no, the sentence is wrong for
   an internal reason too — it means you are stating more than the evidence supports.

## Rewrites

| Instead of | Write |
|---|---|
| The bank **lacks** covenant monitoring | Covenant monitoring is **purchased and not yet activated** |
| **Failure to** govern agent creation | Governance **is in place at the sanctioned tool**; the unsanctioned path is **still open** |
| Data quality is **poor** | Data quality rules are **embedded in the delivery lifecycle**; **coverage extends to 7 of 12 sources** |
| The client has **no** AI strategy | The AI framework is **board-reviewed**; **the operating cadence behind it is the next step** |
| **Weak** customer experience capability | Capability is **deepest in governance and thinnest at the customer edge** — the pillar ordering is the finding |
| They are **behind** their peers | The peer set has moved on this; **the pattern is available and the substrate is already built** |
| **Insufficient** evidence | The ladder ran and returned nothing; **the artefact that would settle it is X** |
| **Nobody owns** the agent estate | An owner per agent **is the output of one AI Council session** |
| Their onboarding is **broken** | Digital onboarding **excludes the segment that defines the franchise** — the exclusion is stated on their own page |
| **Underinvested** in data | Infrastructure was **built expressly to enable AI**, per the executive who owns it — **the opportunity is breadth, not foundation** |

## The opening rule — a field never starts with an absence

Naming the asset first is not a preference about paragraph order. It is a rule about the
**first sentence of every prose field**, because that sentence is what the reader meets
before deciding what kind of document this is — and on several surfaces it is the only
sentence they meet at all. A recommendation card line-clamps `root_cause` to three lines;
a cell drawer opens on the first line of `synthesis`; a leadership row shows
`enrichment_basis` under the name. The rest of the paragraph is below the fold.

**A prose field may not open with an absence construction:**

```
No X…            There is no…        There are no…
Nothing…         None…               Neither…        Nowhere…
Lacks…  Lacking…                     Without a…      Absent…
```

This shipped to a client, on a recommendation card, as the first thing read:

> **No integration platform** appears in a scan of more than two hundred technologies. One
> low-code tool carries point-to-point connections between the core, origination, voice and
> digital-banking platforms, while the packaged connector for this exact core sits on the
> vendor marketplace undeployed.

Everything in it is true and cited, and the second sentence already contains the asset. The
repair is order, not content:

> **One low-code tool** carries the point-to-point connections between core, origination,
> voice and digital banking, and the packaged connector for this exact core is on the vendor
> marketplace waiting to be deployed. No integration platform sits above them — across a scan
> of more than two hundred technologies.

Two more from the same run, with their repairs:

| Shipped | Write |
|---|---|
| **No contact route stored:** the enrichment search returned no profile whose TITLE matched this person | The name and role come from the assessment package; the enrichment search returned no TITLE-matched profile, so the contact route stays null |
| **Nothing BCU publishes** packages a dataset as a product with a named consumer, a service level and a version | An executive owns the member data estate and names it in public; what is not yet published is a dataset packaged as a product, with a named consumer, a service level and a version |

**Later sentences are exempt, and deliberately so.** A field whose first sentence names the
asset and whose second states the absence is this rule working. Measured over one promoted
run, 116 sentences opened with an absence and 109 of them were exactly that shape:

> A member attribute at BCU can travel from Episys through Salesforce into a marketing
> audience or a service conversation, and every hop is a place lineage would be recorded.
> **No catalogue, no lineage tool, no impact-analysis practice appears anywhere in the
> record.** What can be reconstructed is the platform chain; what cannot is the path of any
> particular field through it.

One exemption, and it is the contract's: where nothing grounds a cost of inaction, the
recommendation contract dictates the literal string `no dated trigger established`. Write
what the contract says.

## The pattern behind every rewrite

**Name what exists before naming what does not.** Almost every gap sits beside something the
institution has already built, bought or decided. Lead with that, and the gap becomes the next
step rather than an indictment.

The strongest example from a completed assessment:

> So the score is **1.71, not because capability is thin, but because coverage is narrow**.
> […] **The opportunity is breadth, not foundation.** The bank does not need to be persuaded
> that AI matters, taught to govern it, or sold an infrastructure programme. It needs the
> capability it has already built extended into the workflows where it is absent.

That paragraph delivers a low score, an honest diagnosis and a commercial argument without a
single accusatory clause.

## Steelman before you conclude

Every opportunity carries the counter-argument, stated at its strongest, and then what
defeats it:

> **CHALLENGE.** The steelman: these are low-risk personal productivity artefacts and
> inventorying them is overhead. The falsifier is the bank's own risk framing — shadow AI
> *"going rogue on you and you don't know what it's doing"*, unchallenged in the room. The
> steelman holds for a static estate and fails for one growing weekly.

This does three things at once: it proves you considered the client's likely objection, it
sources the falsifier from the client's own words rather than your judgement, and it bounds
the claim honestly. Do this on every recommendation and every opportunity.

## Language that is required, not optional

Some honesty is not negotiable and must not be softened away:

| Keep | Because |
|---|---|
| Thin-evidence markers | An assessment that states its own weakness is more credible than one that appears complete |
| Quarantine notes | A dash with a reason is a smaller cost than a confident wrong figure |
| Failing safeguard gates | Disclosure is the point of the card |
| "Recorded as an open question, not a finding" | Absence of a documented alternative is not evidence of a bad undocumented one |
| Named risk, where evidenced | "A question a regulator can ask in plain language" is fair; "reckless" is not |

Opportunity framing is about the register of the sentence, not the strength of the finding.
Do not soften a risk into vagueness. State it plainly, attach it to evidence, and frame the
response as available rather than overdue.

## Forbidden constructions

Beyond the standing register rules, these read as accusatory on a client surface:

```
lacks · fails to · failure to · neglected · should have · ought to have
inadequate · insufficient · poor · weak · deficient · immature
behind the curve · falling behind · lagging (as a verb about the client)
no one owns · nobody has · has not bothered · overlooked · ignored
```

`LAGGING` as a posture chip is a defined vocabulary value and is fine. "The bank is lagging"
in prose is not.

## Check it

`scripts/check_language.py` scans a payload for these constructions, for fields that open on
an absence, and for gap statements with no adjacent asset.

The opening rule and the sentence-case rule are checks; the rest is a prompt — it finds the
sentence, you decide. Note what the checker cannot do: it reads the first sentence, not the
argument. A field can open on the asset and still read as an indictment, and no regular
expression will tell you that. Read the framing line, the top finding and every
`root_cause` aloud.
