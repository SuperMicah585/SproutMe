-- Flyer / Ticketmaster image URLs for catalog events.
-- Daily scrape wipes Events_table and the `event-images` storage bucket, then rewrites these.

alter table public."Events_table" add column if not exists image_url text;
alter table public."Events_table" add column if not exists image_source text;
alter table public.user_submitted_events add column if not exists image_url text;
alter table public.user_submitted_events add column if not exists image_source text;

comment on column public."Events_table".image_url is
  'Public flyer/poster URL (Ticketmaster CDN or Supabase Storage).';
comment on column public."Events_table".image_source is
  'ticketmaster | og | jsonld | heuristic | ai | hosted';

grant select, insert, update, delete on table public."Events_table" to service_role;
