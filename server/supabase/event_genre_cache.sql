create table if not exists public.event_genre_cache (
  fingerprint text primary key,
  event_name text,
  venue text,
  genre text not null,
  ticket_info text,
  organizer text,
  source_url text,
  updated_at timestamptz not null default now()
);

# Durable fields that survive Events_table wipe+insert (daily scrape).
# Run once on Supabase (SQL editor) before deploy:
#   alter table public.event_genre_cache add column if not exists city text;
#   alter table public.event_genre_cache add column if not exists headliner text;
alter table public.event_genre_cache add column if not exists ticket_info text;
alter table public.event_genre_cache add column if not exists organizer text;
alter table public.event_genre_cache add column if not exists source_url text;
alter table public.event_genre_cache add column if not exists city text;
alter table public.event_genre_cache add column if not exists headliner text;

grant select, insert, update, delete on table public.event_genre_cache to service_role;
