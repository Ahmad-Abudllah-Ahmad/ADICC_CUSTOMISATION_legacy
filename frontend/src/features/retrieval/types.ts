// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction

/** One ranked record returned by the findability search. */
export interface RetrievalResult {
  record_type: string;
  record_id: string;
  title: string;
  snippet: string;
  source_module: string;
  party: string;
  occurred_at: string;
  entity_refs: string[];
  score: number;
  matched_facets: string[];
  provenance: Record<string, unknown>;
}

/** A ranked, faceted view across the project record. */
export interface RetrievalResponse {
  count: number;
  results: RetrievalResult[];
}

/** Facets a caller can constrain a search by. Every field is optional. */
export interface RetrievalQuery {
  text?: string;
  party?: string;
  date_from?: string;
  date_to?: string;
  entity?: string;
  record_type?: string;
  as_of?: string;
}
