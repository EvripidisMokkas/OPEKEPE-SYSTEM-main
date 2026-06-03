-- AgroLedger Greece starter schema.
-- Requires PostgreSQL with PostGIS enabled.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE farmers (
    farmer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tax_identifier TEXT NOT NULL UNIQUE,
    legal_name TEXT NOT NULL,
    farmer_type TEXT NOT NULL CHECK (farmer_type IN ('individual', 'company', 'cooperative')),
    active_farmer BOOLEAN NOT NULL DEFAULT FALSE,
    bank_account_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE land_parcels (
    parcel_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cadastral_reference TEXT,
    declared_owner_farmer_id UUID REFERENCES farmers(farmer_id),
    right_type TEXT NOT NULL CHECK (right_type IN ('owned', 'leased', 'communal', 'other')),
    right_valid_from DATE NOT NULL,
    right_valid_to DATE,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL,
    declared_area_ha NUMERIC(12, 4) NOT NULL CHECK (declared_area_ha >= 0),
    measured_area_ha NUMERIC(12, 4) NOT NULL CHECK (measured_area_ha >= 0),
    eligible_area_ha NUMERIC(12, 4) NOT NULL CHECK (eligible_area_ha >= 0),
    public_land_conflict BOOLEAN NOT NULL DEFAULT FALSE,
    protected_area_conflict BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX land_parcels_geom_idx ON land_parcels USING GIST (geom);

CREATE TABLE parcel_rights_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id UUID NOT NULL REFERENCES land_parcels(parcel_id),
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('title', 'lease', 'cadastral_extract', 'court_order', 'survey', 'other')),
    document_uri TEXT NOT NULL,
    valid_from DATE,
    valid_to DATE,
    verified_by TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE crop_seasons (
    crop_season_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id UUID NOT NULL REFERENCES land_parcels(parcel_id),
    farmer_id UUID NOT NULL REFERENCES farmers(farmer_id),
    claim_year INTEGER NOT NULL CHECK (claim_year BETWEEN 2000 AND 2100),
    production_type TEXT NOT NULL,
    crop_variety TEXT,
    labelled_area_ha NUMERIC(12, 4) NOT NULL CHECK (labelled_area_ha >= 0),
    organic_status BOOLEAN NOT NULL DEFAULT FALSE,
    irrigation_status TEXT NOT NULL CHECK (irrigation_status IN ('rainfed', 'irrigated', 'mixed', 'unknown')),
    expected_yield_tonnes NUMERIC(12, 4),
    declared_yield_tonnes NUMERIC(12, 4),
    verified_yield_tonnes NUMERIC(12, 4),
    sowing_date DATE,
    harvest_date DATE,
    label_confidence NUMERIC(5, 4) CHECK (label_confidence BETWEEN 0 AND 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (parcel_id, farmer_id, claim_year, production_type)
);

CREATE TABLE remote_sensing_observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id UUID NOT NULL REFERENCES land_parcels(parcel_id),
    claim_year INTEGER NOT NULL CHECK (claim_year BETWEEN 2000 AND 2100),
    provider TEXT NOT NULL,
    observation_type TEXT NOT NULL CHECK (observation_type IN ('ndvi', 'evi', 'crop_classification', 'flood', 'drought', 'burn', 'boundary_change')),
    observation_date DATE NOT NULL,
    confidence NUMERIC(5, 4) CHECK (confidence BETWEEN 0 AND 1),
    result JSONB NOT NULL,
    evidence_uri TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE first_sale_records (
    first_sale_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crop_season_id UUID NOT NULL REFERENCES crop_seasons(crop_season_id),
    invoice_number TEXT NOT NULL,
    buyer_tax_identifier TEXT NOT NULL,
    sale_date DATE NOT NULL,
    product_type TEXT NOT NULL,
    quantity_tonnes NUMERIC(12, 4) NOT NULL CHECK (quantity_tonnes >= 0),
    unit_price_eur NUMERIC(12, 4) NOT NULL CHECK (unit_price_eur >= 0),
    gross_amount_eur NUMERIC(14, 2) NOT NULL CHECK (gross_amount_eur >= 0),
    tax_amount_eur NUMERIC(14, 2) NOT NULL CHECK (tax_amount_eur >= 0),
    mydata_mark TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (invoice_number, buyer_tax_identifier)
);

CREATE TABLE subsidy_claims (
    subsidy_claim_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farmer_id UUID NOT NULL REFERENCES farmers(farmer_id),
    claim_year INTEGER NOT NULL CHECK (claim_year BETWEEN 2000 AND 2100),
    status TEXT NOT NULL CHECK (status IN ('draft', 'submitted', 'under_review', 'held', 'approved', 'paid', 'rejected', 'appealed', 'recovered')),
    risk_score NUMERIC(5, 4) CHECK (risk_score BETWEEN 0 AND 1),
    submitted_at TIMESTAMPTZ,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE subsidy_line_items (
    subsidy_line_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subsidy_claim_id UUID NOT NULL REFERENCES subsidy_claims(subsidy_claim_id),
    parcel_id UUID NOT NULL REFERENCES land_parcels(parcel_id),
    crop_season_id UUID REFERENCES crop_seasons(crop_season_id),
    scheme_code TEXT NOT NULL,
    production_type TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    eligible_area_ha NUMERIC(12, 4) NOT NULL CHECK (eligible_area_ha >= 0),
    rate_eur_per_ha NUMERIC(12, 4) NOT NULL CHECK (rate_eur_per_ha >= 0),
    gross_amount_eur NUMERIC(14, 2) NOT NULL CHECK (gross_amount_eur >= 0),
    reductions_eur NUMERIC(14, 2) NOT NULL DEFAULT 0 CHECK (reductions_eur >= 0),
    final_amount_eur NUMERIC(14, 2) NOT NULL CHECK (final_amount_eur >= 0),
    hold_reason TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE debt_accounts (
    debt_account_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farmer_id UUID NOT NULL REFERENCES farmers(farmer_id),
    debt_type TEXT NOT NULL CHECK (debt_type IN ('tax', 'social_security', 'bank', 'cooperative', 'recovery_order', 'other')),
    principal_eur NUMERIC(14, 2) NOT NULL CHECK (principal_eur >= 0),
    outstanding_eur NUMERIC(14, 2) NOT NULL CHECK (outstanding_eur >= 0),
    status TEXT NOT NULL CHECK (status IN ('open', 'restructured', 'offset_pending', 'closed', 'disputed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE crisis_events (
    crisis_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL CHECK (event_type IN ('drought', 'flood', 'fire', 'frost', 'heat', 'storm', 'disease', 'market_shock', 'other')),
    name TEXT NOT NULL,
    claim_year INTEGER NOT NULL CHECK (claim_year BETWEEN 2000 AND 2100),
    event_start DATE NOT NULL,
    event_end DATE,
    affected_geom GEOMETRY(MultiPolygon, 4326),
    policy_rule_version TEXT NOT NULL,
    declared_by TEXT NOT NULL,
    declared_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX crisis_events_affected_geom_idx ON crisis_events USING GIST (affected_geom);

CREATE TABLE compensation_claims (
    compensation_claim_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crisis_event_id UUID NOT NULL REFERENCES crisis_events(crisis_event_id),
    farmer_id UUID NOT NULL REFERENCES farmers(farmer_id),
    parcel_id UUID NOT NULL REFERENCES land_parcels(parcel_id),
    production_type TEXT NOT NULL,
    affected_area_ha NUMERIC(12, 4) NOT NULL CHECK (affected_area_ha >= 0),
    damage_percent NUMERIC(5, 2) NOT NULL CHECK (damage_percent BETWEEN 0 AND 100),
    calculated_amount_eur NUMERIC(14, 2) NOT NULL CHECK (calculated_amount_eur >= 0),
    final_amount_eur NUMERIC(14, 2) NOT NULL CHECK (final_amount_eur >= 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'submitted', 'under_review', 'approved', 'paid', 'rejected', 'appealed', 'recovered')),
    evidence JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
    audit_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    event_hash TEXT NOT NULL,
    previous_event_hash TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
