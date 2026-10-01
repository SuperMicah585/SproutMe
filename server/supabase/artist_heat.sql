-- Artist listen heat cache (ListenBrainz counts, MusicBrainz ids).
-- Survives the daily Events_table wipe.
-- Daily job inserts unseen headliners. Weekly job refreshes everyone and appends snapshots.

create table if not exists public.artist_heat_cache (
  artist_key text primary key,
  query text not null,
  spotify_id text,
  mbid text,
  display_name text,
  popularity integer,
  followers integer,
  prev_popularity integer,
  prev_followers integer,
  rise_score numeric,
  fetched_at timestamptz not null default now(),
  prev_fetched_at timestamptz,
  updated_at timestamptz not null default now()
);

alter table public.artist_heat_cache add column if not exists mbid text;

create index if not exists artist_heat_cache_spotify_id_idx
  on public.artist_heat_cache (spotify_id);

create index if not exists artist_heat_cache_mbid_idx
  on public.artist_heat_cache (mbid);

create index if not exists artist_heat_cache_fetched_at_idx
  on public.artist_heat_cache (fetched_at);

create table if not exists public.artist_heat_snapshots (
  id bigint generated always as identity primary key,
  artist_key text not null,
  spotify_id text,
  popularity integer,
  followers integer,
  fetched_at timestamptz not null default now()
);

create index if not exists artist_heat_snapshots_artist_fetched_idx
  on public.artist_heat_snapshots (artist_key, fetched_at desc);

grant select, insert, update, delete on table public.artist_heat_cache to service_role;
grant select, insert, update, delete on table public.artist_heat_snapshots to service_role;
