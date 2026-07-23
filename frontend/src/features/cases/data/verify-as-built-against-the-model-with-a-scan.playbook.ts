// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Verify as-built against the model with a scan".
//
// Load the site scan, overlay the design model to spot where the build has
// drifted, and raise an inspection wherever the work sits out of tolerance.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "verify-as-built-against-the-model-with-a-scan",
  order: 332,
  category: "bim",
  companyTypes: ["bim-consultant", "general-contractor", "designer"],
  icon: "Crosshair",
  titleKey: "cases.verify_as_built_against_the_model_with_a_scan.title",
  titleDefault: "Verify as-built against the model with a scan",
  descKey: "cases.verify_as_built_against_the_model_with_a_scan.desc",
  descDefault:
    "Load the site scan, overlay the design model to spot where the build has drifted from the model, and raise an inspection wherever the as-built sits outside tolerance.",
  estMinutes: 9,
  steps: [
    {
      id: "scan",
      icon: "Box",
      inputs: [
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.scan.in.cloud",
          label: "Point cloud file",
        },
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.scan.in.coords",
          label: "Project coordinates",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.scan.out.scan",
          label: "Registered scan",
        },
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.scan.out.aligned",
          label: "Scan on project grid",
        },
      ],
      titleKey:
        "cases.verify_as_built_against_the_model_with_a_scan.step.scan.title",
      titleDefault: "Load the site scan",
      whatKey:
        "cases.verify_as_built_against_the_model_with_a_scan.step.scan.what",
      whatDefault:
        "Bring the laser scan or photogrammetry point cloud of the as-built area into the viewer and set it to the project coordinates so it lands where the model expects it.",
      whyKey:
        "cases.verify_as_built_against_the_model_with_a_scan.step.scan.why",
      whyDefault:
        "A scan referenced to the wrong origin lines up with nothing and every deviation reads as false. Getting the survey onto the project grid first is what makes the whole comparison trustworthy.",
      moduleLabel: "Point Cloud",
      to: "/pointcloud",
    },
    {
      id: "overlay",
      icon: "Layers",
      inputs: [
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.overlay.in.scan",
          label: "Registered scan",
        },
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.overlay.in.model",
          label: "Design model",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.overlay.out.overlay",
          label: "Model-scan overlay",
        },
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.overlay.out.deviation",
          label: "Measured deviations",
        },
      ],
      titleKey:
        "cases.verify_as_built_against_the_model_with_a_scan.step.overlay.title",
      titleDefault: "Overlay the model on the scan",
      whatKey:
        "cases.verify_as_built_against_the_model_with_a_scan.step.overlay.what",
      whatDefault:
        "Load the design model in the same view as the point cloud and walk the overlay, looking for where the built surface sits proud of or behind the modelled element.",
      whyKey:
        "cases.verify_as_built_against_the_model_with_a_scan.step.overlay.why",
      whyDefault:
        "The scan is the ground truth of what was actually built. Laying the model over it turns a vague feeling that something is off into a measured deviation you can point at.",
      moduleLabel: "BIM Viewer",
      to: "/projects/:projectId/bim",
    },
    {
      id: "inspect",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.inspect.in.deviation",
          label: "Measured deviations",
        },
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.inspect.in.tolerance",
          label: "Tolerance limits",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.inspect.out.inspection",
          label: "Inspection raised",
        },
        {
          labelKey:
            "cases.verify_as_built_against_the_model_with_a_scan.step.inspect.out.record",
          label: "Deviation record",
        },
      ],
      titleKey:
        "cases.verify_as_built_against_the_model_with_a_scan.step.inspect.title",
      titleDefault: "Raise an inspection out of tolerance",
      whatKey:
        "cases.verify_as_built_against_the_model_with_a_scan.step.inspect.what",
      whatDefault:
        "Where the build sits outside the allowed tolerance, raise an inspection against that location with the measured deviation and a photo or scan clip attached.",
      whyKey:
        "cases.verify_as_built_against_the_model_with_a_scan.step.inspect.why",
      whyDefault:
        "A deviation nobody records gets buried the moment the next trade covers it. An inspection puts the out-of-tolerance work on a list that has to be answered before it is closed over.",
      moduleLabel: "Inspections",
      to: "/projects/:projectId/inspections",
    },
  ],
};

export default playbook;
