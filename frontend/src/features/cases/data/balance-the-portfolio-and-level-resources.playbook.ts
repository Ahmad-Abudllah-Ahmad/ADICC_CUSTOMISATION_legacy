// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Balance the portfolio and level resources".
//
// See every live project and what it demands on one board, compare that demand
// to the crews and plant you actually have, then move resources across projects
// to take the peaks out. Content strings are key plus inline English default.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "balance-the-portfolio-and-level-resources",
  order: 322,
  category: "planning",
  companyTypes: ["general-contractor", "project-manager"],
  icon: "Boxes",
  titleKey: "cases.balance_the_portfolio_and_level_resources.title",
  titleDefault: "Balance the portfolio and level resources",
  descKey: "cases.balance_the_portfolio_and_level_resources.desc",
  descDefault:
    "See every live project and what it demands on one board, compare that demand to the crews and plant you actually have, then move resources across projects to take the peaks out before they bite.",
  estMinutes: 9,
  steps: [
    {
      id: "board",
      icon: "Table2",
      inputs: [
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.board.in.projects",
          label: "Live projects",
        },
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.board.in.programmes",
          label: "Project programmes",
        },
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.board.in.milestones",
          label: "Key milestones",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.board.out.board",
          label: "Portfolio board",
        },
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.board.out.demand",
          label: "Resource demand per project",
        },
      ],
      titleKey:
        "cases.balance_the_portfolio_and_level_resources.step.board.title",
      titleDefault: "See the whole portfolio",
      whatKey:
        "cases.balance_the_portfolio_and_level_resources.step.board.what",
      whatDefault:
        "Open the portfolio board and read every live project on one screen, with its programme, milestones and the resource demand each one is placing on the business.",
      whyKey: "cases.balance_the_portfolio_and_level_resources.step.board.why",
      whyDefault:
        "Projects planned one at a time each look fine and still collectively ask for three cranes on the same Monday. Seeing them together is the only way to spot the clash before it lands.",
      moduleLabel: "Portfolio",
      moduleLabelKey: "portfolio.title",
      to: "/portfolio",
    },
    {
      id: "capacity",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.capacity.in.demand",
          label: "Committed work demand",
        },
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.capacity.in.crews",
          label: "Available crews & plant",
        },
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.capacity.in.calendar",
          label: "Weekly calendar",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.capacity.out.chart",
          label: "Demand vs capacity chart",
        },
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.capacity.out.overloads",
          label: "Flagged overload weeks",
        },
      ],
      titleKey:
        "cases.balance_the_portfolio_and_level_resources.step.capacity.title",
      titleDefault: "Compare demand to capacity",
      whatKey:
        "cases.balance_the_portfolio_and_level_resources.step.capacity.what",
      whatDefault:
        "Lay the committed work across all projects against the crews, gangs and plant actually available, week by week, and mark where demand runs past what you have.",
      whyKey:
        "cases.balance_the_portfolio_and_level_resources.step.capacity.why",
      whyDefault:
        "A week where four projects all want the same gang is a week something slips, whether you planned for it or not. Naming the overload early turns it into a decision instead of a surprise.",
      moduleLabel: "Capacity planning",
      moduleLabelKey: "nav.capacity_planning",
      to: "/portfolio/capacity",
    },
    {
      id: "level",
      icon: "Scale",
      inputs: [
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.level.in.overloads",
          label: "Overload weeks",
        },
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.level.in.float",
          label: "Available float",
        },
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.level.in.milestones",
          label: "Fixed milestones",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.level.out.leveled",
          label: "Leveled plan",
        },
        {
          labelKey:
            "cases.balance_the_portfolio_and_level_resources.step.level.out.moves",
          label: "Resource reassignments",
        },
      ],
      titleKey:
        "cases.balance_the_portfolio_and_level_resources.step.level.title",
      titleDefault: "Level the peaks out",
      whatKey:
        "cases.balance_the_portfolio_and_level_resources.step.level.what",
      whatDefault:
        "Move resources between projects, re-sequence the float you have and shift start dates to pull the demand under the capacity line without breaking the key milestones.",
      whyKey: "cases.balance_the_portfolio_and_level_resources.step.level.why",
      whyDefault:
        "Chasing a peak with hired plant and agency labour is the most expensive way to build. Leveling the work across the portfolio first spends your own resources before you pay a premium for someone else.",
      moduleLabel: "Resource leveling",
      moduleLabelKey: "nav.resource_leveling",
      to: "/portfolio/leveling",
    },
  ],
};

export default playbook;
