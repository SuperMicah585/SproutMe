-- Venue Google Places cache. Survives the daily Events_table wipe.
-- Refresh only for a new venue_key, or when fetched_at is older than 6 months.

create table if not exists public.venue_place_cache (
  venue_key text primary key,
  query text not null,
  city text,
  venue text,
  place_id text,
  display_name text,
  rating numeric,
  user_rating_count integer,
  types text[] not null default '{}',
  editorial_summary text,
  review_summary text,
  reviews jsonb not null default '[]'::jsonb,
  lat double precision,
  lng double precision,
  fetched_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.venue_place_cache
  add column if not exists lat double precision;

alter table public.venue_place_cache
  add column if not exists lng double precision;

create index if not exists venue_place_cache_fetched_at_idx
  on public.venue_place_cache (fetched_at);

create index if not exists venue_place_cache_city_idx
  on public.venue_place_cache (city);

create index if not exists venue_place_cache_geo_idx
  on public.venue_place_cache (lat, lng)
  where lat is not null and lng is not null;

grant select, insert, update, delete on table public.venue_place_cache to service_role;
