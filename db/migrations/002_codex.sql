-- 002: codex as its own entity.
--
-- MANUSCRIPTS!K 'Codex unique identifier' repeats across every text copy bound
-- in the same codex, so it is a reference table, not a string on manuscript.
--
-- Deliberately (codex_id, name) only. The codex-level attributes still living
-- on manuscript (holding institution, shelfmark, height/width, dating, type,
-- origin, ...) are NOT hoisted here yet: 7-16% of the multi-row codices
-- disagree with themselves on those columns in the workbook. They move in a
-- later migration, once the researchers have resolved the conflicts listed in
-- the backfill report.
--
-- manuscript.codex_identifier and manuscript.codex_number are left untouched
-- so this change loses nothing and stays reversible.

CREATE TABLE public.codex (
    codex_id integer NOT NULL,
    name character varying NOT NULL
);

CREATE SEQUENCE public.codex_codex_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

ALTER SEQUENCE public.codex_codex_id_seq OWNED BY public.codex.codex_id;

ALTER TABLE ONLY public.codex
    ALTER COLUMN codex_id SET DEFAULT nextval('public.codex_codex_id_seq'::regclass);

ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_pkey PRIMARY KEY (codex_id);

ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_name_key UNIQUE (name);

COMMENT ON TABLE public.codex
    IS 'One physical codex. Excel MANUSCRIPTS → ''Codex unique identifier'', deduplicated.';
COMMENT ON COLUMN public.codex.name
    IS 'Excel MANUSCRIPTS → ''Codex unique identifier''';

ALTER TABLE public.manuscript ADD COLUMN codex_id integer;

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_codex_id_fkey FOREIGN KEY (codex_id)
    REFERENCES public.codex(codex_id);

CREATE INDEX ix_manuscript_codex_id ON public.manuscript USING btree (codex_id);

COMMENT ON COLUMN public.manuscript.codex_id
    IS 'The codex this copy is bound in; resolved from ''Codex unique identifier''';
