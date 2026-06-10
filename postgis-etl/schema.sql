-- AgriforestryOS PostGIS spatial mirror — schema (Sprint 5).
--
-- One table per mirrored farmOS asset type. Each row carries the farmOS
-- asset UUID as the primary key (back-reference + idempotency key) and a
-- geometry stored in EPSG:26917 (NAD83 UTM 17N) so spatial queries return
-- distances in metres. The ETL reprojects from farmOS's WGS84 on insert.
--
-- Safe to run repeatedly: everything is IF NOT EXISTS.

CREATE EXTENSION IF NOT EXISTS postgis;

-- Trees ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trees (
    asset_uuid       text PRIMARY KEY,
    name             text,
    species          text,
    variety          text,
    dbh_cm           numeric,
    height_m         numeric,
    canopy_radius_m  numeric,
    stratum          text,
    succession_stage text,
    health_status    text,
    planting_date    timestamptz,
    tenure           text,
    odoo_lot         text,
    geom             geometry(Point, 26917),
    synced_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS trees_geom_gix ON trees USING GIST (geom);
CREATE INDEX IF NOT EXISTS trees_species_idx ON trees (species);

-- Infrastructure ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS infrastructure (
    asset_uuid          text PRIMARY KEY,
    name                text,
    infrastructure_type text,
    condition           text,
    material            text,
    capacity            text,
    geom                geometry(Geometry, 26917),
    synced_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS infrastructure_geom_gix ON infrastructure USING GIST (geom);

-- Tree plantings (rows / guilds / consortia) --------------------------------
CREATE TABLE IF NOT EXISTS plantings (
    asset_uuid        text PRIMARY KEY,
    name              text,
    planting_type     text,
    succession_stage  text,
    geom              geometry(Geometry, 26917),
    synced_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS plantings_geom_gix ON plantings USING GIST (geom);

-- Land areas ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS land_areas (
    asset_uuid  text PRIMARY KEY,
    name        text,
    land_type   text,
    geom        geometry(Geometry, 26917),
    synced_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS land_areas_geom_gix ON land_areas USING GIST (geom);
