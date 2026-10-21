-- 003: publication as its own entity.
--
-- EDITIONS!E 'Edition unique identifier (inc. volume)' names one published
-- volume and repeats across every edition row printed in it, so it is a
-- reference table, not a string on edition.
--
-- Deliberately (publication_id, name) only, for the same reason as codex:
-- within a single publication name the workbook disagrees with itself on
-- 'Edition number (inc. volume) in database' (9 names), 'Publication year'
-- (18) and 'Edition reference' (46). Those columns move here in a later
-- migration once the researchers have resolved the conflicts.
--
-- Unrelated to the existing edition.publication_year column, which stays.

CREATE TABLE public.publication (
    publication_id integer NOT NULL,
    name character varying NOT NULL
);

CREATE SEQUENCE public.publication_publication_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

ALTER SEQUENCE public.publication_publication_id_seq
    OWNED BY public.publication.publication_id;

ALTER TABLE ONLY public.publication
    ALTER COLUMN publication_id
    SET DEFAULT nextval('public.publication_publication_id_seq'::regclass);

ALTER TABLE ONLY public.publication
    ADD CONSTRAINT publication_pkey PRIMARY KEY (publication_id);

ALTER TABLE ONLY public.publication
    ADD CONSTRAINT publication_name_key UNIQUE (name);

COMMENT ON TABLE public.publication
    IS 'One published volume. Excel EDITIONS → ''Edition unique identifier (inc. volume)'', deduplicated.';
COMMENT ON COLUMN public.publication.name
    IS 'Excel EDITIONS → ''Edition unique identifier (inc. volume)''';

ALTER TABLE public.edition ADD COLUMN publication_id integer;

ALTER TABLE ONLY public.edition
    ADD CONSTRAINT edition_publication_id_fkey FOREIGN KEY (publication_id)
    REFERENCES public.publication(publication_id);

CREATE INDEX ix_edition_publication_id ON public.edition USING btree (publication_id);

COMMENT ON COLUMN public.edition.publication_id
    IS 'The volume this edition is printed in; resolved from ''Edition unique identifier (inc. volume)''';
