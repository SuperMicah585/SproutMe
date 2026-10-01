-- Clean billed artist/DJ list extracted at scrape time.
-- Keeps event_name as the display title; headliner is for heat/score/search matching.
-- Prefer JSON list storage, e.g. ["Bassvictim","Thoom"]
-- (legacy rows may still be a single name or comma-separated text).

alter table public."Events_table" add column if not exists headliner text;
alter table public.user_submitted_events add column if not exists headliner text;

create index if not exists events_table_headliner_idx
  on public."Events_table" (headliner);

grant select, insert, update, delete on table public."Events_table" to service_role;
