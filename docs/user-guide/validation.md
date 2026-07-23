# The validation pipeline

Validation is not an afterthought in this platform, it is a built-in step in the workflow. Every import and every estimate can be checked against configurable rule sets, and the result is a plain traffic-light report that tells you what is clean, what needs a look, and what must be fixed before you go on.

## What it is for

The pipeline catches the errors that quietly wreck an estimate: a position with a quantity but no rate, a zero price, a duplicate line, a missing trade, a classification that does not follow the standard, a quantity that does not match the geometry it came from. Catching these early, and linking each one straight back to the position or element that caused it, is far cheaper than finding them after a tender has gone out.

## When it runs

Validation is part of the core sequence: import, parse, validate, enrich, store. It runs when data comes in from a CAD or BIM conversion, and again over the estimate itself. You can also run it on demand at any time while you work, so you are never guessing at the state of the BOQ.

## What it checks

Rules are grouped into sets you enable per project. The built-in sets cover the common measurement and classification standards, including DIN 276, NRM, MasterFormat and GAEB, alongside universal quality checks that apply to any BOQ, checks on converted BIM and CAD data such as required properties and geometry validity, and completeness checks that ask whether every trade is covered and whether the scope looks whole. You can also define your own rules for project or client-specific requirements.

## Reading the result

Each rule produces one of three outcomes: pass, warning, or error. Warnings flag something worth a look; errors are the ones that should block a submission. The report rolls these into an overall quality score from zero to one hundred so you can see at a glance whether an estimate is in good shape, and every individual finding links to the exact BOQ position, drawing region or model element it refers to, so fixing it is one click away.

## The steps

1. Choose the rule sets for the project, based on the region and standard you are working to.
2. Run the validation, on demand or as part of an import. Read the traffic-light summary and the overall score.
3. Work through the errors first, then the warnings, using the link on each finding to jump to the position that needs fixing.
4. Re-run until the score and the report say the estimate is ready, then export or tender with the validation report as evidence of quality.

## Requirements and quality gates

Beyond rule-based validation, the requirements workflow captures project requirements as structured entity, attribute and constraint triplets, for example that a wall's fire rating must be at least a given class, and runs them through sequential quality gates for completeness, consistency, coverage and compliance. Each requirement can be traced to the BOQ positions that satisfy it, so you can show that the estimate actually covers what was specified.

## How it connects

Validation touches almost everything. It scores the [bill of quantities](./estimating-and-boq.md), checks quantities from [takeoff](./quantity-takeoff.md) and converted models from [BIM](./bim-to-cost-and-carbon.md), and gates the data that [planning and cost control](./planning-and-cost-control.md) relies on. Because it is a first-class step rather than an optional extra, the numbers the rest of the platform builds on stay trustworthy.
