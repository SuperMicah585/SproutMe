-- SMS conversation memory: durable taste rules + rolling message window.
-- Run in Supabase SQL editor if the table already exists.

create table if not exists public.sms_conversations (
  phone_number text primary key,
  messages jsonb not null default '[]'::jsonb,
  started_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  global_rules text not null default '',
  rules_updated_at timestamptz
);

alter table public.sms_conversations
  add column if not exists global_rules text not null default '';

alter table public.sms_conversations
  add column if not exists rules_updated_at timestamptz;

grant select, insert, update, delete on table public.sms_conversations to service_role;
