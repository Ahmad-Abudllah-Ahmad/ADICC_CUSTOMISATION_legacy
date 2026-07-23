# World cost bases and multi-base comparison

Construction prices are local. The same wall costs a different amount in Berlin, London, São Paulo or Shanghai, and it is quoted in a different currency against a different measurement standard. The platform ships national cost databases so you can price a job with real local rates, and it lets you compare the same scope across regions.

## What it is for

Two jobs, really. The first is to give an estimator a credible local rate without hunting for it: tens of thousands of priced construction items, covering the major trades, available for many regions and translated into more than twenty languages. The second is comparison: to see how a rate, a package or a whole scope changes when you move it from one national base to another, and to keep every currency honest while you do it.

## The cost data you get

The bundled CWICR database holds more than 55,000 cost items across the main construction trades, with national price sets for regions including the DACH countries, the United Kingdom, the United States, France, Spain, Italy, Brazil, Russia and the CIS, the Gulf, China and India, among others. Each item carries a unit, a rate and a resource composition, and many are broken down into the labour, material and equipment that make up the rate. You can browse a regional catalog directly, search it, and apply an item to a BOQ position.

## Search, compare and substitute

The Cost Explorer is a search-first workspace over the cost and resource databases. Beyond finding an item by description or code, it lets you find priced work by the resources it consumes, compare the same scope across regional price bases, and substitute one resource for another to see how the rate moves. It is built on a reverse index from resources back to the work that uses them, so a question like which items use this material, and what would happen to their rates if its price changed, has a direct answer.

## Currency, indices and honesty

Prices in different bases are in different currencies, and the platform never silently blends them. Portfolio and comparison figures are grouped by currency rather than added together across currencies. Built-in exchange rates, including purchasing-power adjustment where appropriate, let you convert or compare deliberately. A separate price-index capability adjusts historical rates forward or between locations so a base from one time or place can be brought onto a common footing before you compare.

## The steps

1. On a project, pick the region so the estimate defaults to the right base, currency and classification standard.
2. Search the cost base from the BOQ and apply rates to positions, or browse the regional catalog to explore what is available.
3. To compare, open the Cost Explorer, take a scope or a set of items, and view them across more than one regional base. Read the spread, and use resource substitution to test a what-if on a rate.
4. Where currencies differ, convert with the built-in rates or keep them grouped, and apply a price index when you need to align rates across time or location.

## Bring your own rates

You are not limited to the bundled data. You can import your own cost database from Excel or CSV, or connect one through the API, and it then behaves like any other base. See [importing your own cost database](../cost-database-import.md) for the format and the steps.

## How it connects

Cost bases feed rates into the [bill of quantities](./estimating-and-boq.md) and into [element matching](./bim-to-cost-and-carbon.md). The same priced scope drives [design option comparison](./design-options.md), where cost per option is compared, and [tendering](./tendering-and-bids.md), where your priced base becomes the yardstick against which subcontractor bids are read.
