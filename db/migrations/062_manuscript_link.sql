-- 062: new manuscript_link / manuscript_link_type for links about one text copy.
--
-- 061 moved the existing links to codex level (codex_link). These two new,
-- empty tables hold links that really are about a single manuscript copy (a
-- page-level image, a copy-specific description, …). The researchers create
-- the link types themselves in Mathesar; none are seeded.
--
-- Same shape as codex_link / codex_link_type. The url column becomes Mathesar's
-- uri domain where Mathesar is installed (as 004–006 did for the other link
-- tables); on a database built from db/migrations/ alone it stays character
-- varying. The file explorer does not track this table (yet).

CREATE TABLE public.manuscript_link_type (
    manuscript_link_type_id   SERIAL PRIMARY KEY,
    manuscript_link_type      character varying NOT NULL UNIQUE,
    manuscript_link_type_note character varying
);

CREATE TABLE public.manuscript_link (
    manuscript_link_id      SERIAL PRIMARY KEY,
    manuscript_id           integer NOT NULL REFERENCES public.manuscript (manuscript_id),
    manuscript_link_type_id integer NOT NULL REFERENCES public.manuscript_link_type (manuscript_link_type_id),
    manuscript_link_url     character varying NOT NULL,
    manuscript_link_note    character varying
);
CREATE INDEX ix_manuscript_link_manuscript_id ON public.manuscript_link (manuscript_id);

DO $$
DECLARE
    editor CONSTANT text := 'hagiographies_editor';
BEGIN
    -- The table is empty, so a plain cast is safe (004 explains msar.cast_to_uri).
    IF EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE n.nspname = 'mathesar_types' AND t.typname = 'uri') THEN
        ALTER TABLE public.manuscript_link
            ALTER COLUMN manuscript_link_url TYPE mathesar_types.uri;
    ELSE
        RAISE NOTICE 'mathesar_types.uri not present; manuscript_link_url stays character varying';
    END IF;

    -- 007's default privileges only cover tables created by the role that ran
    -- 007; grant explicitly so it does not matter who runs this migration.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = editor) THEN
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.manuscript_link, public.manuscript_link_type TO %I', editor);
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE public.manuscript_link_manuscript_link_id_seq, public.manuscript_link_type_manuscript_link_type_id_seq TO %I', editor);
    END IF;
END
$$;
