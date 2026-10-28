-- Run once in Supabase Dashboard -> SQL Editor. Safe to re-run (idempotent).
-- Access model: ONLY the backend (service-role key) reads/writes, except users may read their own documents.

create table if not exists public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  status text not null default 'pending' check (status in ('pending','approved','suspended')),
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  role text not null default 'user' check (role in ('user','org','admin')),
  org_id uuid references public.organizations(id) on delete set null,
  status text not null default 'active' check (status in ('active','suspended')),
  created_at timestamptz not null default now()
);

create table if not exists public.documents (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  filename text not null,
  sha256 text not null,
  storage_path text not null,
  mime text not null,
  reference_no text,
  institute_name text,
  risk_score int not null,
  risk_level text not null,
  result jsonb not null,
  created_at timestamptz not null default now()
);
-- columns added by the verification upgrade (no-ops on a fresh install)
alter table public.documents add column if not exists academic_year text;
alter table public.documents add column if not exists valid_upto text;
alter table public.documents add column if not exists verification_status text;
alter table public.documents add column if not exists trust_score int;
alter table public.documents add column if not exists org_id uuid references public.organizations(id) on delete set null;
alter table public.documents add column if not exists review_status text not null default 'clear';
alter table public.documents add column if not exists finding_counts jsonb not null default '{}'::jsonb;
alter table public.documents add column if not exists review_notes jsonb not null default '[]'::jsonb;
create index if not exists documents_user_idx on public.documents(user_id, created_at desc);
create index if not exists documents_sha_idx on public.documents(sha256);
create index if not exists documents_ref_idx on public.documents(reference_no);
create index if not exists documents_org_idx on public.documents(org_id, created_at desc);

-- Letters an organization has actually issued: the ground truth uploads are matched against.
create table if not exists public.registry_records (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  reference_no text not null,
  institute_name text not null,
  academic_year text,
  issue_date text,
  valid_upto text,
  permanent_id text,
  courses jsonb not null default '[]'::jsonb,
  sha256 text,
  expected_watermark text,
  notes text,
  status text not null default 'active' check (status in ('active','revoked')),
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);
create index if not exists registry_ref_idx on public.registry_records(reference_no);
create index if not exists registry_org_idx on public.registry_records(org_id);

-- Published findings. 'snapshot' holds only verdict/findings/mismatches: no uploader identity, no file name.
create table if not exists public.published_reports (
  id uuid primary key default gen_random_uuid(),
  document_id uuid references public.documents(id) on delete set null,
  org_id uuid references public.organizations(id) on delete set null,
  published_by uuid references auth.users(id) on delete set null,
  published_by_email text,
  title text not null,
  note text,
  scope text not null default 'public' check (scope in ('public','org')),
  status text not null default 'published' check (status in ('published','withdrawn')),
  snapshot jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.audit_log (
  id bigint generated always as identity primary key,
  actor_id uuid,
  actor_email text,
  action text not null,
  target text,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- Share links: a frozen, identity-free snapshot reachable without login via an unguessable token (revocable, expiring).
create table if not exists public.share_links (
  id uuid primary key default gen_random_uuid(),
  token text not null unique,
  document_id uuid not null references public.documents(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  snapshot jsonb not null,
  expires_at timestamptz not null,
  revoked boolean not null default false,
  views int not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists share_doc_idx on public.share_links(document_id);

alter table public.organizations enable row level security;
alter table public.share_links enable row level security;  -- no policy: only the backend (service role) touches it
alter table public.profiles enable row level security;
alter table public.documents enable row level security;
alter table public.registry_records enable row level security;
alter table public.published_reports enable row level security;
alter table public.audit_log enable row level security;
-- Only the owner may read their documents directly; everything else has NO policy => no browser access.
drop policy if exists "own rows readable" on public.documents;
create policy "own rows readable" on public.documents for select using (auth.uid() = user_id);

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('documents', 'documents', false, 10485760, array['application/pdf','image/png','image/jpeg'])
on conflict (id) do nothing;

-- Measured impact baseline (admin-entered from the pre-deployment process; never pre-filled)
create table if not exists public.impact_baselines (
  id uuid primary key default gen_random_uuid(),
  baseline_duplicate_cases int not null check (baseline_duplicate_cases > 0),
  period_label text not null,
  post_start date not null,
  source_note text not null default '',
  set_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);
alter table public.impact_baselines enable row level security;  -- no policy: backend (service role) only
