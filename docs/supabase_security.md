# Supabase: close the automatic web API (Row Level Security)

Supabase automatically puts a web API in front of every table in the `public` schema. Anyone holding the
project's public "anon" key can use it. Class Compass never uses that API (it talks to the database
directly), but if Row Level Security (RLS) is off, the API could read every table, including pupils.

Turning RLS on **with no rules** closes the API completely. The app keeps working, because it connects as
the account that owns the tables, and owners are not restricted by RLS. This was checked on PostgreSQL 16
with a test owner account and a test "API" account: the owner still saw the rows, the other account saw none.

## 1. Check

Supabase dashboard → your project → **Advisors → Security Advisor**. Errors called
"RLS Disabled in Public" mean the API is open for those tables. You can also run this in **SQL Editor**:

```sql
select tablename, rowsecurity from pg_tables where schemaname = 'public' order by tablename;
```

`rowsecurity = false` means open.

## 2. Fix (take a backup first — see `docs/backup_restore.md`)

In **SQL Editor**, run:

```sql
do $$
declare r record;
begin
  for r in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', r.tablename);
  end loop;
end $$;
```

Then open the live site and check that sign-in, a dashboard and a pupil page still load.

## 3. If anything stops working

This undoes it straight away (same SQL Editor):

```sql
do $$
declare r record;
begin
  for r in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I disable row level security', r.tablename);
  end loop;
end $$;
```

That would mean the app is connecting as a different account from the one that owns the tables. Ask
before trying anything else.

## 4. Later

Tables added by future migrations start with RLS off. Re-run step 1 after deploys that add tables, or ask for
a migration that switches RLS on automatically for new tables.
