# Quantity takeoff from drawings and models

Takeoff is how you get quantities out of the documents a project actually arrives in: PDF drawings, 2D CAD files, and 3D BIM models. The platform measures from all of them and pushes the numbers straight into the bill of quantities, so you do not retype anything.

## What it is for

The goal of takeoff is a reliable quantity with a trail back to where it came from. Instead of scaling a paper drawing and keying a number into a spreadsheet, you measure on screen, the measurement carries its own units and source, and it becomes a BOQ quantity that anyone can audit later. Every measurement stays linked to the drawing region or the model element it was read from.

## When to use it

Use PDF takeoff when all you have is a drawing set, which is the common case early in a job or for a subcontract package. Use DWG takeoff when you have the 2D CAD file and want to measure real geometry and work by layer. Use BIM takeoff when a 3D model exists, because a model gives you area, volume and length for many elements at once rather than one measurement at a time.

## The steps

1. Upload the document to the project. The platform detects the format and opens the right viewer: a page viewer for PDFs, a 2D viewer for DWG and DXF, and a 3D viewer for models.
2. For a PDF, set the scale once per page by drawing a line of known length, then measure distances, areas and counts. For a DWG, click a polyline to read its area, perimeter and segment lengths in place, and work layer by layer. For a model, the quantities are already in the geometry.
3. For a model, choose how to group the extracted elements, for example by category, type, level or family, so the numbers land in a structure that matches your BOQ.
4. Send a measurement to the BOQ. A PDF or DWG measurement becomes a position quantity. For a model, use the quantity picker to take area, volume or length from the linked elements, with the source parameter shown next to the unit, and link many elements to a single BOQ line when they represent the same work.
5. Review anything the AI proposed. When you take off from a photo, a description or a scanned drawing, the AI returns a suggested scope with confidence scores. Confirm or correct each item before it is applied.

## How it connects

Takeoff feeds the [bill of quantities](./estimating-and-boq.md) directly, and it is the front door to the [BIM to cost and carbon](./bim-to-cost-and-carbon.md) workflow, where converted model quantities are matched to rates. Element matching maps a measured or modelled item to a cost position and scales the underlying resources into the estimate. The [validation pipeline](./validation.md) then checks the quantities for consistency against the geometry they came from.

## Reality capture

For work that only exists on site, the point cloud and reality capture capability ingests laser scan, photogrammetry and LiDAR exports and turns a registered cloud into human-confirmed, validation-gated quantities and progress. As everywhere else, the scan proposes and a person confirms before a number reaches the estimate.
