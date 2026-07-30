-- 000_init: baseline schema.
--
-- The research schema exactly as it stood on 2026-07-29, before any
-- migration was applied. Generated with:
--
--   pg_dump --no-owner --no-privileges --schema-only --schema=public
--
-- against the QAS server (PostgreSQL 14), then stripped of the psql
-- preamble. It exists so the full schema is legible from the code and so an
-- empty database can be built from db/migrations/ alone.
--
-- On a database that already holds this schema the runner records 000 as
-- applied WITHOUT executing it. This file is frozen: later schema changes
-- are new numbered migrations, never edits here.


--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA IF NOT EXISTS public;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: archdiocese; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archdiocese (
    archdiocese_id integer NOT NULL,
    name character varying NOT NULL,
    location_id integer,
    note character varying
);


--
-- Name: COLUMN archdiocese.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.archdiocese.name IS 'Excel TEXTS → ''Text creation - location by archdiocese''';


--
-- Name: archdiocese_archdiocese_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archdiocese_archdiocese_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archdiocese_archdiocese_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archdiocese_archdiocese_id_seq OWNED BY public.archdiocese.archdiocese_id;


--
-- Name: author; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.author (
    author_id integer NOT NULL,
    name character varying NOT NULL,
    institutional_training_ground character varying,
    regional_antecedents character varying,
    author_milieu_id integer,
    note character varying
);


--
-- Name: COLUMN author.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.author.name IS 'Excel TEXTS → ''Author of the text''';


--
-- Name: COLUMN author.institutional_training_ground; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.author.institutional_training_ground IS 'Excel TEXTS → ''Institutional training ground of the author''';


--
-- Name: COLUMN author.regional_antecedents; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.author.regional_antecedents IS 'Excel TEXTS → ''Regional or local antecedents of the author''';


--
-- Name: COLUMN author.author_milieu_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.author.author_milieu_id IS 'Excel TEXTS → ''Author milieu''';


--
-- Name: author_author_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.author_author_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: author_author_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.author_author_id_seq OWNED BY public.author.author_id;


--
-- Name: author_milieu; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.author_milieu (
    author_milieu_id integer NOT NULL,
    label character varying NOT NULL,
    note character varying
);


--
-- Name: COLUMN author_milieu.label; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.author_milieu.label IS 'Excel TEXTS → ''Author milieu''';


--
-- Name: author_milieu_author_milieu_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.author_milieu_author_milieu_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: author_milieu_author_milieu_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.author_milieu_author_milieu_id_seq OWNED BY public.author_milieu.author_milieu_id;


--
-- Name: dating_confidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dating_confidence (
    dating_confidence_id integer NOT NULL,
    label character varying NOT NULL,
    notes character varying
);


--
-- Name: COLUMN dating_confidence.label; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.dating_confidence.label IS 'Excel TEXTS → ''Dating confidence rating''';


--
-- Name: dating_confidence_dating_confidence_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dating_confidence_dating_confidence_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dating_confidence_dating_confidence_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dating_confidence_dating_confidence_id_seq OWNED BY public.dating_confidence.dating_confidence_id;


--
-- Name: diocese; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diocese (
    diocese_id integer NOT NULL,
    name character varying NOT NULL,
    location_id integer,
    note character varying
);


--
-- Name: COLUMN diocese.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.diocese.name IS 'Excel TEXTS → ''Text creation - location by diocese''';


--
-- Name: diocese_diocese_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diocese_diocese_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diocese_diocese_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diocese_diocese_id_seq OWNED BY public.diocese.diocese_id;


--
-- Name: edition; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.edition (
    edition_id integer NOT NULL,
    text_id integer,
    identifier_per_text character varying NOT NULL,
    publication_year integer,
    reference character varying,
    page_numbers character varying,
    reprint boolean,
    reprint_identical boolean,
    reprint_of_edition_id integer,
    reprint_of character varying,
    collation_done boolean,
    general_notes character varying
);


--
-- Name: COLUMN edition.text_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition.text_id IS 'Excel EDITIONS → ''Unique identifier (NULL when the reference is unresolvable; see general_notes)''';


--
-- Name: COLUMN edition.identifier_per_text; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition.identifier_per_text IS 'Excel EDITIONS → ''''BHL or NO BHL'' prefix + ''_'' + ''Edition unique identifier per individual text''''';


--
-- Name: COLUMN edition.publication_year; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition.publication_year IS 'Excel EDITIONS → ''Publication year''';


--
-- Name: COLUMN edition.reference; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition.reference IS 'Excel EDITIONS → ''Edition reference''';


--
-- Name: COLUMN edition.page_numbers; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition.page_numbers IS 'Excel EDITIONS → ''Page numbers''';


--
-- Name: COLUMN edition.reprint; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition.reprint IS 'Excel EDITIONS → ''Reprint ?''';


--
-- Name: COLUMN edition.reprint_identical; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition.reprint_identical IS 'Excel EDITIONS → ''If reprint, identically typeset?''';


--
-- Name: COLUMN edition.reprint_of_edition_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition.reprint_of_edition_id IS 'Excel EDITIONS → ''If reprint, of what? (resolved)''';


--
-- Name: COLUMN edition.reprint_of; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition.reprint_of IS 'Excel EDITIONS → ''If reprint, of what?''';


--
-- Name: COLUMN edition.collation_done; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition.collation_done IS 'Excel EDITIONS → ''Collation done?''';


--
-- Name: COLUMN edition.general_notes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition.general_notes IS 'Excel EDITIONS → ''Notes''';


--
-- Name: edition__edition; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.edition__edition (
    edition__edition_id integer NOT NULL,
    edition_id integer NOT NULL,
    consulted_edition_id integer NOT NULL,
    notes character varying
);


--
-- Name: COLUMN edition__edition.edition_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition__edition.edition_id IS 'Excel EDITIONS → ''Edition used or consulted 1–5 (row)''';


--
-- Name: COLUMN edition__edition.consulted_edition_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition__edition.consulted_edition_id IS 'Excel EDITIONS → ''Edition used or consulted 1–5 (resolved)''';


--
-- Name: edition__edition_edition__edition_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.edition__edition_edition__edition_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: edition__edition_edition__edition_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.edition__edition_edition__edition_id_seq OWNED BY public.edition__edition.edition__edition_id;


--
-- Name: edition__manuscripts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.edition__manuscripts (
    edition__manuscripts_id integer NOT NULL,
    edition_id integer NOT NULL,
    manuscript_id integer NOT NULL,
    likely_use_of_a_copy boolean,
    notes character varying
);


--
-- Name: COLUMN edition__manuscripts.edition_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition__manuscripts.edition_id IS 'Excel EDITIONS → ''Manuscript used 1–16 (row)''';


--
-- Name: COLUMN edition__manuscripts.manuscript_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition__manuscripts.manuscript_id IS 'Excel EDITIONS → ''Manuscript used 1–16 (resolved)''';


--
-- Name: COLUMN edition__manuscripts.likely_use_of_a_copy; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition__manuscripts.likely_use_of_a_copy IS 'Excel EDITIONS → ''Likely use of a copy of Manuscript 1–16?''';


--
-- Name: edition__manuscripts_edition__manuscripts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.edition__manuscripts_edition__manuscripts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: edition__manuscripts_edition__manuscripts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.edition__manuscripts_edition__manuscripts_id_seq OWNED BY public.edition__manuscripts.edition__manuscripts_id;


--
-- Name: edition_edition_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.edition_edition_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: edition_edition_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.edition_edition_id_seq OWNED BY public.edition.edition_id;


--
-- Name: edition_link; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.edition_link (
    edition_link_id integer NOT NULL,
    edition_id integer NOT NULL,
    edition_link_type_id integer NOT NULL,
    url character varying NOT NULL,
    note character varying
);


--
-- Name: COLUMN edition_link.edition_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition_link.edition_id IS 'Excel EDITIONS → ''Edition images link (row)''';


--
-- Name: COLUMN edition_link.edition_link_type_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition_link.edition_link_type_id IS 'Excel EDITIONS → ''Images of edition? → type''';


--
-- Name: COLUMN edition_link.url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.edition_link.url IS 'Excel EDITIONS → ''''Edition images link'' hyperlink target''';


--
-- Name: edition_link_edition_link_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.edition_link_edition_link_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: edition_link_edition_link_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.edition_link_edition_link_id_seq OWNED BY public.edition_link.edition_link_id;


--
-- Name: edition_link_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.edition_link_type (
    edition_link_type_id integer NOT NULL,
    label character varying NOT NULL,
    note character varying
);


--
-- Name: edition_link_type_edition_link_type_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.edition_link_type_edition_link_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: edition_link_type_edition_link_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.edition_link_type_edition_link_type_id_seq OWNED BY public.edition_link_type.edition_link_type_id;


--
-- Name: institution; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.institution (
    institution_id integer NOT NULL,
    name character varying NOT NULL,
    location_id integer,
    note character varying
);


--
-- Name: COLUMN institution.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.institution.name IS 'Excel TEXTS → ''''Text creation - location by institution'' / ''Primary institutional destinatary''''';


--
-- Name: institution_institution_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.institution_institution_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: institution_institution_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.institution_institution_id_seq OWNED BY public.institution.institution_id;


--
-- Name: location; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.location (
    location_id integer NOT NULL,
    name character varying,
    latitude double precision,
    longitude double precision
);


--
-- Name: COLUMN location.latitude; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.location.latitude IS 'Excel TEXTS → ''… GPS Longitude (sic, swapped) / 1e6''';


--
-- Name: COLUMN location.longitude; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.location.longitude IS 'Excel TEXTS → ''… GPS Latitude (sic, swapped) / 1e6''';


--
-- Name: location_location_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.location_location_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: location_location_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.location_location_id_seq OWNED BY public.location.location_id;


--
-- Name: manuscript; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manuscript (
    manuscript_id integer NOT NULL,
    identifier character varying NOT NULL,
    text_id integer,
    codex_number integer,
    codex_identifier character varying,
    codex_multiple_copies boolean,
    codex_copy_amount integer,
    manuscript_preservation_status_id integer,
    location_id integer,
    manuscript_holding_institution_id integer,
    height character varying,
    width character varying,
    dating_century integer,
    dating_range_start integer,
    dating_range_end integer,
    dating_reference character varying,
    dating_confidence_id integer,
    dating_note character varying,
    codex_legendiers_usable boolean,
    codex_composite boolean,
    codex_legendiers_entry_code character varying,
    codex_notes character varying,
    vernacular_region_id integer,
    origin_archdiocese_id integer,
    origin_diocese_id integer,
    origin_diocese_confidence_rating_id integer,
    origin_institution_id integer,
    origin_institution_confidence_rating_id integer,
    provenance_early_institute_id integer,
    provenance_early_confidence_id integer,
    provenance_later_institute_id integer,
    provenance_later_confidence_id integer,
    origin_or_provenance_secondary_reference character varying,
    manuscript_type_id integer,
    manuscript_type_note character varying,
    general_notes character varying
);


--
-- Name: COLUMN manuscript.identifier; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.identifier IS 'Excel MANUSCRIPTS → ''''BHL or NO BHL'' + ''_'' + ''Manuscript copy unique identifier per text'' (workbook duplicates are imported as-is and warned)''';


--
-- Name: COLUMN manuscript.text_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.text_id IS 'Excel MANUSCRIPTS → ''Unique text identifier (NULL when the reference is unresolvable; see general_notes)''';


--
-- Name: COLUMN manuscript.codex_number; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.codex_number IS 'Excel MANUSCRIPTS → ''Codex number in database''';


--
-- Name: COLUMN manuscript.codex_identifier; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.codex_identifier IS 'Excel MANUSCRIPTS → ''Codex unique identifier''';


--
-- Name: COLUMN manuscript.codex_multiple_copies; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.codex_multiple_copies IS 'Excel MANUSCRIPTS → ''Codex with multiple manuscript copies of texts from corpus''';


--
-- Name: COLUMN manuscript.codex_copy_amount; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.codex_copy_amount IS 'Excel MANUSCRIPTS → ''Codex features n manuscript copies of texts from corpus''';


--
-- Name: COLUMN manuscript.manuscript_preservation_status_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.manuscript_preservation_status_id IS 'Excel MANUSCRIPTS → ''Preservation status of manuscript copy''';


--
-- Name: COLUMN manuscript.location_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.location_id IS 'Excel MANUSCRIPTS → ''Manuscript location''';


--
-- Name: COLUMN manuscript.manuscript_holding_institution_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.manuscript_holding_institution_id IS 'Excel MANUSCRIPTS → ''Manuscript holding institution''';


--
-- Name: COLUMN manuscript.height; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.height IS 'Excel MANUSCRIPTS → ''Manuscript height''';


--
-- Name: COLUMN manuscript.width; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.width IS 'Excel MANUSCRIPTS → ''Manuscript width''';


--
-- Name: COLUMN manuscript.dating_century; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.dating_century IS 'Excel MANUSCRIPTS → ''Manuscript dating by (earliest) century''';


--
-- Name: COLUMN manuscript.dating_range_start; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.dating_range_start IS 'Excel MANUSCRIPTS → ''Manuscript dating range start (0 when not an integer in the workbook)''';


--
-- Name: COLUMN manuscript.dating_range_end; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.dating_range_end IS 'Excel MANUSCRIPTS → ''Manuscript dating range end (0 when not an integer in the workbook)''';


--
-- Name: COLUMN manuscript.dating_reference; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.dating_reference IS 'Excel MANUSCRIPTS → ''Preferred secondary reference for manuscript dating (hyperlink URL when the cell is hyperlinked)''';


--
-- Name: COLUMN manuscript.dating_confidence_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.dating_confidence_id IS 'Excel MANUSCRIPTS → ''Confidence rating for manuscript dating''';


--
-- Name: COLUMN manuscript.dating_note; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.dating_note IS 'Excel MANUSCRIPTS → ''raw ''Manuscript dating range start/end'' when not integers''';


--
-- Name: COLUMN manuscript.codex_legendiers_usable; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.codex_legendiers_usable IS 'Excel MANUSCRIPTS → ''Usable Légendiers entry for codex contents''';


--
-- Name: COLUMN manuscript.codex_composite; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.codex_composite IS 'Excel MANUSCRIPTS → ''Composite?''';


--
-- Name: COLUMN manuscript.codex_legendiers_entry_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.codex_legendiers_entry_code IS 'Excel MANUSCRIPTS → ''Légendiers entry code''';


--
-- Name: COLUMN manuscript.codex_notes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.codex_notes IS 'Excel MANUSCRIPTS → ''Notes on codex contents''';


--
-- Name: COLUMN manuscript.vernacular_region_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.vernacular_region_id IS 'Excel MANUSCRIPTS → ''Vernacular region (Romance/Germanic)''';


--
-- Name: COLUMN manuscript.origin_archdiocese_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.origin_archdiocese_id IS 'Excel MANUSCRIPTS → ''Manuscript origin by archdiocese''';


--
-- Name: COLUMN manuscript.origin_diocese_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.origin_diocese_id IS 'Excel MANUSCRIPTS → ''Manuscript origin by diocese''';


--
-- Name: COLUMN manuscript.origin_diocese_confidence_rating_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.origin_diocese_confidence_rating_id IS 'Excel MANUSCRIPTS → ''Manuscript origin by diocese confidence rating''';


--
-- Name: COLUMN manuscript.origin_institution_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.origin_institution_id IS 'Excel MANUSCRIPTS → ''Manuscript origin by institution''';


--
-- Name: COLUMN manuscript.origin_institution_confidence_rating_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.origin_institution_confidence_rating_id IS 'Excel MANUSCRIPTS → ''Manuscript origin confidence rating''';


--
-- Name: COLUMN manuscript.provenance_early_institute_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.provenance_early_institute_id IS 'Excel MANUSCRIPTS → ''Manuscript provenance by early/earliest institutional owner (second occurrence of this duplicated header)''';


--
-- Name: COLUMN manuscript.provenance_early_confidence_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.provenance_early_confidence_id IS 'Excel MANUSCRIPTS → ''Manuscript provenance by early/earliest institutional owner confidence rating (second occurrence of this duplicated header)''';


--
-- Name: COLUMN manuscript.provenance_later_institute_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.provenance_later_institute_id IS 'Excel MANUSCRIPTS → ''Manuscript provenance by undetermined or later institutional owner''';


--
-- Name: COLUMN manuscript.provenance_later_confidence_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.provenance_later_confidence_id IS 'Excel MANUSCRIPTS → ''no source column yet (the workbook has no confidence rating for the undetermined/later owner) — always NULL for now''';


--
-- Name: COLUMN manuscript.origin_or_provenance_secondary_reference; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.origin_or_provenance_secondary_reference IS 'Excel MANUSCRIPTS → ''Manuscript origin and provenance preferred secondary reference (hyperlink URL when the cell is hyperlinked)''';


--
-- Name: COLUMN manuscript.manuscript_type_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.manuscript_type_id IS 'Excel MANUSCRIPTS → ''Manuscript type (whitespace-normalized label)''';


--
-- Name: COLUMN manuscript.manuscript_type_note; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.manuscript_type_note IS 'Excel MANUSCRIPTS → ''Manuscript type (raw cell, incl. notes on type selection)''';


--
-- Name: COLUMN manuscript.general_notes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript.general_notes IS 'Excel MANUSCRIPTS → ''''Notes'', prefixed with the raw ''Unique text identifier'' when it resolves to no text''';


--
-- Name: manuscript_holding_institution; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manuscript_holding_institution (
    manuscript_holding_institution_id integer NOT NULL,
    name character varying NOT NULL
);


--
-- Name: COLUMN manuscript_holding_institution.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript_holding_institution.name IS 'Excel MANUSCRIPTS → ''Manuscript holding institution''';


--
-- Name: manuscript_holding_institutio_manuscript_holding_institutio_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manuscript_holding_institutio_manuscript_holding_institutio_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: manuscript_holding_institutio_manuscript_holding_institutio_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manuscript_holding_institutio_manuscript_holding_institutio_seq OWNED BY public.manuscript_holding_institution.manuscript_holding_institution_id;


--
-- Name: manuscript_link; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manuscript_link (
    manuscript_link_id integer NOT NULL,
    manuscript_id integer NOT NULL,
    manuscript_link_type_id integer NOT NULL,
    url character varying NOT NULL,
    note character varying
);


--
-- Name: COLUMN manuscript_link.manuscript_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript_link.manuscript_id IS 'Excel MANUSCRIPTS → ''link columns (row)''';


--
-- Name: COLUMN manuscript_link.manuscript_link_type_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript_link.manuscript_link_type_id IS 'Excel MANUSCRIPTS → ''link column → type''';


--
-- Name: COLUMN manuscript_link.url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript_link.url IS 'Excel MANUSCRIPTS → ''link cell hyperlink target''';


--
-- Name: manuscript_link_manuscript_link_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manuscript_link_manuscript_link_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: manuscript_link_manuscript_link_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manuscript_link_manuscript_link_id_seq OWNED BY public.manuscript_link.manuscript_link_id;


--
-- Name: manuscript_link_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manuscript_link_type (
    manuscript_link_type_id integer NOT NULL,
    label character varying NOT NULL,
    note character varying
);


--
-- Name: manuscript_link_type_manuscript_link_type_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manuscript_link_type_manuscript_link_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: manuscript_link_type_manuscript_link_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manuscript_link_type_manuscript_link_type_id_seq OWNED BY public.manuscript_link_type.manuscript_link_type_id;


--
-- Name: manuscript_manuscript_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manuscript_manuscript_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: manuscript_manuscript_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manuscript_manuscript_id_seq OWNED BY public.manuscript.manuscript_id;


--
-- Name: manuscript_preservation_status; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manuscript_preservation_status (
    manuscript_preservation_status_id integer NOT NULL,
    label character varying NOT NULL
);


--
-- Name: COLUMN manuscript_preservation_status.label; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript_preservation_status.label IS 'Excel MANUSCRIPTS → ''Preservation status of manuscript copy''';


--
-- Name: manuscript_preservation_statu_manuscript_preservation_statu_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manuscript_preservation_statu_manuscript_preservation_statu_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: manuscript_preservation_statu_manuscript_preservation_statu_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manuscript_preservation_statu_manuscript_preservation_statu_seq OWNED BY public.manuscript_preservation_status.manuscript_preservation_status_id;


--
-- Name: manuscript_relation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manuscript_relation (
    manuscript_relation_id integer NOT NULL,
    manuscript_id integer NOT NULL,
    related_manuscript_id integer NOT NULL,
    manuscript_relationship_type_id integer NOT NULL,
    note character varying
);


--
-- Name: COLUMN manuscript_relation.manuscript_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript_relation.manuscript_id IS 'Excel MANUSCRIPTS → ''''Based on exemplar'' / ''Exemplar of which manuscript(s)'' (row)''';


--
-- Name: COLUMN manuscript_relation.related_manuscript_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript_relation.related_manuscript_id IS 'Excel MANUSCRIPTS → ''''Based on exemplar'' / ''Exemplar of which manuscript(s)'' (resolved)''';


--
-- Name: COLUMN manuscript_relation.manuscript_relationship_type_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript_relation.manuscript_relationship_type_id IS 'Excel MANUSCRIPTS → ''source column → type''';


--
-- Name: manuscript_relation_manuscript_relation_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manuscript_relation_manuscript_relation_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: manuscript_relation_manuscript_relation_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manuscript_relation_manuscript_relation_id_seq OWNED BY public.manuscript_relation.manuscript_relation_id;


--
-- Name: manuscript_relationship_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manuscript_relationship_type (
    manuscript_relationship_type_id integer NOT NULL,
    label character varying NOT NULL,
    note character varying
);


--
-- Name: manuscript_relationship_type_manuscript_relationship_type_i_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manuscript_relationship_type_manuscript_relationship_type_i_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: manuscript_relationship_type_manuscript_relationship_type_i_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manuscript_relationship_type_manuscript_relationship_type_i_seq OWNED BY public.manuscript_relationship_type.manuscript_relationship_type_id;


--
-- Name: manuscript_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manuscript_type (
    manuscript_type_id integer NOT NULL,
    label character varying NOT NULL,
    note character varying
);


--
-- Name: COLUMN manuscript_type.label; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.manuscript_type.label IS 'Excel MANUSCRIPTS → ''Manuscript type (whitespace-normalized)''';


--
-- Name: manuscript_type_manuscript_type_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manuscript_type_manuscript_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: manuscript_type_manuscript_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manuscript_type_manuscript_type_id_seq OWNED BY public.manuscript_type.manuscript_type_id;


--
-- Name: origin_confidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.origin_confidence (
    origin_confidence_id integer NOT NULL,
    label character varying NOT NULL,
    note character varying
);


--
-- Name: COLUMN origin_confidence.label; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.origin_confidence.label IS 'Excel MANUSCRIPTS → ''''Manuscript origin by diocese confidence rating'' / ''Manuscript origin confidence rating''''';


--
-- Name: origin_confidence_origin_confidence_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.origin_confidence_origin_confidence_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: origin_confidence_origin_confidence_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.origin_confidence_origin_confidence_id_seq OWNED BY public.origin_confidence.origin_confidence_id;


--
-- Name: provenance_confidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provenance_confidence (
    provenance_confidence_id integer NOT NULL,
    label character varying NOT NULL,
    note character varying
);


--
-- Name: COLUMN provenance_confidence.label; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.provenance_confidence.label IS 'Excel MANUSCRIPTS → ''Manuscript provenance by early/earliest institutional owner confidence rating''';


--
-- Name: provenance_confidence_provenance_confidence_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provenance_confidence_provenance_confidence_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provenance_confidence_provenance_confidence_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provenance_confidence_provenance_confidence_id_seq OWNED BY public.provenance_confidence.provenance_confidence_id;


--
-- Name: repertory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.repertory (
    repertory_id integer NOT NULL,
    name character varying NOT NULL,
    note character varying
);


--
-- Name: repertory_link; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.repertory_link (
    repertory_link_id integer NOT NULL,
    text_id integer NOT NULL,
    repertory_id integer NOT NULL,
    url text,
    note character varying
);


--
-- Name: repertory_link_repertory_link_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.repertory_link_repertory_link_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: repertory_link_repertory_link_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.repertory_link_repertory_link_id_seq OWNED BY public.repertory_link.repertory_link_id;


--
-- Name: repertory_repertory_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.repertory_repertory_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: repertory_repertory_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.repertory_repertory_id_seq OWNED BY public.repertory.repertory_id;


--
-- Name: text; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.text (
    text_id integer NOT NULL,
    identifier character varying NOT NULL,
    title character varying,
    approximate_token_count integer,
    text_form_id integer,
    text_source_type_id integer,
    text_source_subtype_id integer,
    reecriture boolean,
    reecriture_text_id integer,
    reecriture_note character varying,
    dating_range_start integer,
    dating_range_stop integer,
    dating_range character varying,
    dating_confidence_id integer,
    dating_note character varying,
    author_id integer,
    author_in_destinary_institution boolean,
    creation_archdiocese_id integer,
    creation_diocese_id integer,
    creation_institution_id integer,
    creation_note character varying,
    destinary_archdiocese_id integer,
    destinary_diocese_id integer,
    destinary_institution_id integer,
    destinary_note character varying,
    reference character varying,
    general_note character varying
);


--
-- Name: COLUMN text.identifier; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.identifier IS 'Excel TEXTS → ''''BHL or NO BHL'' + ''_'' + ''Unique identifier''''';


--
-- Name: COLUMN text.title; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.title IS 'Excel TEXTS → ''Title of the work''';


--
-- Name: COLUMN text.approximate_token_count; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.approximate_token_count IS 'Excel TEXTS → ''Approximate token count''';


--
-- Name: COLUMN text.text_form_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.text_form_id IS 'Excel TEXTS → ''Prose or verse''';


--
-- Name: COLUMN text.text_source_type_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.text_source_type_id IS 'Excel TEXTS → ''Source type''';


--
-- Name: COLUMN text.text_source_subtype_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.text_source_subtype_id IS 'Excel TEXTS → ''Subtype''';


--
-- Name: COLUMN text.reecriture; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.reecriture IS 'Excel TEXTS → ''Réécriture?''';


--
-- Name: COLUMN text.reecriture_text_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.reecriture_text_id IS 'Excel TEXTS → ''Réécriture of which text(s)? (resolved)''';


--
-- Name: COLUMN text.reecriture_note; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.reecriture_note IS 'Excel TEXTS → ''Réécriture of which text(s)?''';


--
-- Name: COLUMN text.dating_range_start; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.dating_range_start IS 'Excel TEXTS → ''Dating range (beginning)''';


--
-- Name: COLUMN text.dating_range_stop; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.dating_range_stop IS 'Excel TEXTS → ''Dating range (end)''';


--
-- Name: COLUMN text.dating_range; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.dating_range IS 'Excel TEXTS → ''Quarter century chronology''';


--
-- Name: COLUMN text.dating_confidence_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.dating_confidence_id IS 'Excel TEXTS → ''Dating confidence rating''';


--
-- Name: COLUMN text.dating_note; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.dating_note IS 'Excel TEXTS → ''Dating notes''';


--
-- Name: COLUMN text.author_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.author_id IS 'Excel TEXTS → ''Author of the text''';


--
-- Name: COLUMN text.author_in_destinary_institution; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.author_in_destinary_institution IS 'Excel TEXTS → ''Is author based in destinatary institution?''';


--
-- Name: COLUMN text.creation_archdiocese_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.creation_archdiocese_id IS 'Excel TEXTS → ''Text creation - location by archdiocese''';


--
-- Name: COLUMN text.creation_diocese_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.creation_diocese_id IS 'Excel TEXTS → ''Text creation - location by diocese''';


--
-- Name: COLUMN text.creation_institution_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.creation_institution_id IS 'Excel TEXTS → ''Text creation - location by institution''';


--
-- Name: COLUMN text.destinary_institution_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.destinary_institution_id IS 'Excel TEXTS → ''Primary institutional destinatary''';


--
-- Name: COLUMN text.reference; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.reference IS 'Excel TEXTS → ''Selected reference''';


--
-- Name: COLUMN text.general_note; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text.general_note IS 'Excel TEXTS → ''Notes''';


--
-- Name: text_form; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.text_form (
    text_form_id integer NOT NULL,
    label character varying NOT NULL
);


--
-- Name: COLUMN text_form.label; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text_form.label IS 'Excel TEXTS → ''Prose or verse''';


--
-- Name: text_form_text_form_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.text_form_text_form_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: text_form_text_form_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.text_form_text_form_id_seq OWNED BY public.text_form.text_form_id;


--
-- Name: text_source_subtype; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.text_source_subtype (
    text_source_subtype_id integer NOT NULL,
    label character varying NOT NULL
);


--
-- Name: COLUMN text_source_subtype.label; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text_source_subtype.label IS 'Excel TEXTS → ''Subtype''';


--
-- Name: text_source_subtype_text_source_subtype_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.text_source_subtype_text_source_subtype_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: text_source_subtype_text_source_subtype_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.text_source_subtype_text_source_subtype_id_seq OWNED BY public.text_source_subtype.text_source_subtype_id;


--
-- Name: text_source_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.text_source_type (
    text_source_type_id integer NOT NULL,
    label character varying NOT NULL
);


--
-- Name: COLUMN text_source_type.label; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.text_source_type.label IS 'Excel TEXTS → ''Source type''';


--
-- Name: text_source_type_text_source_type_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.text_source_type_text_source_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: text_source_type_text_source_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.text_source_type_text_source_type_id_seq OWNED BY public.text_source_type.text_source_type_id;


--
-- Name: text_text_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.text_text_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: text_text_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.text_text_id_seq OWNED BY public.text.text_id;


--
-- Name: vernacular_region; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vernacular_region (
    vernacular_region_id integer NOT NULL,
    label character varying NOT NULL,
    note character varying
);


--
-- Name: COLUMN vernacular_region.label; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vernacular_region.label IS 'Excel MANUSCRIPTS → ''Vernacular region (Romance/Germanic)''';


--
-- Name: vernacular_region_vernacular_region_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.vernacular_region_vernacular_region_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vernacular_region_vernacular_region_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.vernacular_region_vernacular_region_id_seq OWNED BY public.vernacular_region.vernacular_region_id;


--
-- Name: archdiocese archdiocese_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archdiocese ALTER COLUMN archdiocese_id SET DEFAULT nextval('public.archdiocese_archdiocese_id_seq'::regclass);


--
-- Name: author author_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.author ALTER COLUMN author_id SET DEFAULT nextval('public.author_author_id_seq'::regclass);


--
-- Name: author_milieu author_milieu_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.author_milieu ALTER COLUMN author_milieu_id SET DEFAULT nextval('public.author_milieu_author_milieu_id_seq'::regclass);


--
-- Name: dating_confidence dating_confidence_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dating_confidence ALTER COLUMN dating_confidence_id SET DEFAULT nextval('public.dating_confidence_dating_confidence_id_seq'::regclass);


--
-- Name: diocese diocese_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diocese ALTER COLUMN diocese_id SET DEFAULT nextval('public.diocese_diocese_id_seq'::regclass);


--
-- Name: edition edition_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition ALTER COLUMN edition_id SET DEFAULT nextval('public.edition_edition_id_seq'::regclass);


--
-- Name: edition__edition edition__edition_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition__edition ALTER COLUMN edition__edition_id SET DEFAULT nextval('public.edition__edition_edition__edition_id_seq'::regclass);


--
-- Name: edition__manuscripts edition__manuscripts_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition__manuscripts ALTER COLUMN edition__manuscripts_id SET DEFAULT nextval('public.edition__manuscripts_edition__manuscripts_id_seq'::regclass);


--
-- Name: edition_link edition_link_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition_link ALTER COLUMN edition_link_id SET DEFAULT nextval('public.edition_link_edition_link_id_seq'::regclass);


--
-- Name: edition_link_type edition_link_type_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition_link_type ALTER COLUMN edition_link_type_id SET DEFAULT nextval('public.edition_link_type_edition_link_type_id_seq'::regclass);


--
-- Name: institution institution_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.institution ALTER COLUMN institution_id SET DEFAULT nextval('public.institution_institution_id_seq'::regclass);


--
-- Name: location location_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.location ALTER COLUMN location_id SET DEFAULT nextval('public.location_location_id_seq'::regclass);


--
-- Name: manuscript manuscript_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript ALTER COLUMN manuscript_id SET DEFAULT nextval('public.manuscript_manuscript_id_seq'::regclass);


--
-- Name: manuscript_holding_institution manuscript_holding_institution_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_holding_institution ALTER COLUMN manuscript_holding_institution_id SET DEFAULT nextval('public.manuscript_holding_institutio_manuscript_holding_institutio_seq'::regclass);


--
-- Name: manuscript_link manuscript_link_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_link ALTER COLUMN manuscript_link_id SET DEFAULT nextval('public.manuscript_link_manuscript_link_id_seq'::regclass);


--
-- Name: manuscript_link_type manuscript_link_type_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_link_type ALTER COLUMN manuscript_link_type_id SET DEFAULT nextval('public.manuscript_link_type_manuscript_link_type_id_seq'::regclass);


--
-- Name: manuscript_preservation_status manuscript_preservation_status_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_preservation_status ALTER COLUMN manuscript_preservation_status_id SET DEFAULT nextval('public.manuscript_preservation_statu_manuscript_preservation_statu_seq'::regclass);


--
-- Name: manuscript_relation manuscript_relation_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_relation ALTER COLUMN manuscript_relation_id SET DEFAULT nextval('public.manuscript_relation_manuscript_relation_id_seq'::regclass);


--
-- Name: manuscript_relationship_type manuscript_relationship_type_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_relationship_type ALTER COLUMN manuscript_relationship_type_id SET DEFAULT nextval('public.manuscript_relationship_type_manuscript_relationship_type_i_seq'::regclass);


--
-- Name: manuscript_type manuscript_type_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_type ALTER COLUMN manuscript_type_id SET DEFAULT nextval('public.manuscript_type_manuscript_type_id_seq'::regclass);


--
-- Name: origin_confidence origin_confidence_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.origin_confidence ALTER COLUMN origin_confidence_id SET DEFAULT nextval('public.origin_confidence_origin_confidence_id_seq'::regclass);


--
-- Name: provenance_confidence provenance_confidence_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_confidence ALTER COLUMN provenance_confidence_id SET DEFAULT nextval('public.provenance_confidence_provenance_confidence_id_seq'::regclass);


--
-- Name: repertory repertory_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repertory ALTER COLUMN repertory_id SET DEFAULT nextval('public.repertory_repertory_id_seq'::regclass);


--
-- Name: repertory_link repertory_link_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repertory_link ALTER COLUMN repertory_link_id SET DEFAULT nextval('public.repertory_link_repertory_link_id_seq'::regclass);


--
-- Name: text text_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text ALTER COLUMN text_id SET DEFAULT nextval('public.text_text_id_seq'::regclass);


--
-- Name: text_form text_form_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_form ALTER COLUMN text_form_id SET DEFAULT nextval('public.text_form_text_form_id_seq'::regclass);


--
-- Name: text_source_subtype text_source_subtype_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_source_subtype ALTER COLUMN text_source_subtype_id SET DEFAULT nextval('public.text_source_subtype_text_source_subtype_id_seq'::regclass);


--
-- Name: text_source_type text_source_type_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_source_type ALTER COLUMN text_source_type_id SET DEFAULT nextval('public.text_source_type_text_source_type_id_seq'::regclass);


--
-- Name: vernacular_region vernacular_region_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vernacular_region ALTER COLUMN vernacular_region_id SET DEFAULT nextval('public.vernacular_region_vernacular_region_id_seq'::regclass);


--
-- Name: archdiocese archdiocese_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archdiocese
    ADD CONSTRAINT archdiocese_name_key UNIQUE (name);


--
-- Name: archdiocese archdiocese_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archdiocese
    ADD CONSTRAINT archdiocese_pkey PRIMARY KEY (archdiocese_id);


--
-- Name: author_milieu author_milieu_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.author_milieu
    ADD CONSTRAINT author_milieu_label_key UNIQUE (label);


--
-- Name: author_milieu author_milieu_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.author_milieu
    ADD CONSTRAINT author_milieu_pkey PRIMARY KEY (author_milieu_id);


--
-- Name: author author_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.author
    ADD CONSTRAINT author_name_key UNIQUE (name);


--
-- Name: author author_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.author
    ADD CONSTRAINT author_pkey PRIMARY KEY (author_id);


--
-- Name: dating_confidence dating_confidence_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dating_confidence
    ADD CONSTRAINT dating_confidence_label_key UNIQUE (label);


--
-- Name: dating_confidence dating_confidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dating_confidence
    ADD CONSTRAINT dating_confidence_pkey PRIMARY KEY (dating_confidence_id);


--
-- Name: diocese diocese_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diocese
    ADD CONSTRAINT diocese_name_key UNIQUE (name);


--
-- Name: diocese diocese_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diocese
    ADD CONSTRAINT diocese_pkey PRIMARY KEY (diocese_id);


--
-- Name: edition__edition edition__edition_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition__edition
    ADD CONSTRAINT edition__edition_pkey PRIMARY KEY (edition__edition_id);


--
-- Name: edition__manuscripts edition__manuscripts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition__manuscripts
    ADD CONSTRAINT edition__manuscripts_pkey PRIMARY KEY (edition__manuscripts_id);


--
-- Name: edition_link edition_link_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition_link
    ADD CONSTRAINT edition_link_pkey PRIMARY KEY (edition_link_id);


--
-- Name: edition_link_type edition_link_type_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition_link_type
    ADD CONSTRAINT edition_link_type_label_key UNIQUE (label);


--
-- Name: edition_link_type edition_link_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition_link_type
    ADD CONSTRAINT edition_link_type_pkey PRIMARY KEY (edition_link_type_id);


--
-- Name: edition edition_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition
    ADD CONSTRAINT edition_pkey PRIMARY KEY (edition_id);


--
-- Name: institution institution_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.institution
    ADD CONSTRAINT institution_name_key UNIQUE (name);


--
-- Name: institution institution_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.institution
    ADD CONSTRAINT institution_pkey PRIMARY KEY (institution_id);


--
-- Name: location location_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.location
    ADD CONSTRAINT location_pkey PRIMARY KEY (location_id);


--
-- Name: manuscript_holding_institution manuscript_holding_institution_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_holding_institution
    ADD CONSTRAINT manuscript_holding_institution_name_key UNIQUE (name);


--
-- Name: manuscript_holding_institution manuscript_holding_institution_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_holding_institution
    ADD CONSTRAINT manuscript_holding_institution_pkey PRIMARY KEY (manuscript_holding_institution_id);


--
-- Name: manuscript_link manuscript_link_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_link
    ADD CONSTRAINT manuscript_link_pkey PRIMARY KEY (manuscript_link_id);


--
-- Name: manuscript_link_type manuscript_link_type_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_link_type
    ADD CONSTRAINT manuscript_link_type_label_key UNIQUE (label);


--
-- Name: manuscript_link_type manuscript_link_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_link_type
    ADD CONSTRAINT manuscript_link_type_pkey PRIMARY KEY (manuscript_link_type_id);


--
-- Name: manuscript manuscript_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_pkey PRIMARY KEY (manuscript_id);


--
-- Name: manuscript_preservation_status manuscript_preservation_status_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_preservation_status
    ADD CONSTRAINT manuscript_preservation_status_label_key UNIQUE (label);


--
-- Name: manuscript_preservation_status manuscript_preservation_status_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_preservation_status
    ADD CONSTRAINT manuscript_preservation_status_pkey PRIMARY KEY (manuscript_preservation_status_id);


--
-- Name: manuscript_relation manuscript_relation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_relation
    ADD CONSTRAINT manuscript_relation_pkey PRIMARY KEY (manuscript_relation_id);


--
-- Name: manuscript_relationship_type manuscript_relationship_type_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_relationship_type
    ADD CONSTRAINT manuscript_relationship_type_label_key UNIQUE (label);


--
-- Name: manuscript_relationship_type manuscript_relationship_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_relationship_type
    ADD CONSTRAINT manuscript_relationship_type_pkey PRIMARY KEY (manuscript_relationship_type_id);


--
-- Name: manuscript_type manuscript_type_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_type
    ADD CONSTRAINT manuscript_type_label_key UNIQUE (label);


--
-- Name: manuscript_type manuscript_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_type
    ADD CONSTRAINT manuscript_type_pkey PRIMARY KEY (manuscript_type_id);


--
-- Name: origin_confidence origin_confidence_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.origin_confidence
    ADD CONSTRAINT origin_confidence_label_key UNIQUE (label);


--
-- Name: origin_confidence origin_confidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.origin_confidence
    ADD CONSTRAINT origin_confidence_pkey PRIMARY KEY (origin_confidence_id);


--
-- Name: provenance_confidence provenance_confidence_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_confidence
    ADD CONSTRAINT provenance_confidence_label_key UNIQUE (label);


--
-- Name: provenance_confidence provenance_confidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_confidence
    ADD CONSTRAINT provenance_confidence_pkey PRIMARY KEY (provenance_confidence_id);


--
-- Name: repertory_link repertory_link_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repertory_link
    ADD CONSTRAINT repertory_link_pkey PRIMARY KEY (repertory_link_id);


--
-- Name: repertory repertory_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repertory
    ADD CONSTRAINT repertory_name_key UNIQUE (name);


--
-- Name: repertory repertory_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repertory
    ADD CONSTRAINT repertory_pkey PRIMARY KEY (repertory_id);


--
-- Name: text_form text_form_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_form
    ADD CONSTRAINT text_form_label_key UNIQUE (label);


--
-- Name: text_form text_form_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_form
    ADD CONSTRAINT text_form_pkey PRIMARY KEY (text_form_id);


--
-- Name: text text_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_pkey PRIMARY KEY (text_id);


--
-- Name: text_source_subtype text_source_subtype_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_source_subtype
    ADD CONSTRAINT text_source_subtype_label_key UNIQUE (label);


--
-- Name: text_source_subtype text_source_subtype_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_source_subtype
    ADD CONSTRAINT text_source_subtype_pkey PRIMARY KEY (text_source_subtype_id);


--
-- Name: text_source_type text_source_type_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_source_type
    ADD CONSTRAINT text_source_type_label_key UNIQUE (label);


--
-- Name: text_source_type text_source_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_source_type
    ADD CONSTRAINT text_source_type_pkey PRIMARY KEY (text_source_type_id);


--
-- Name: vernacular_region vernacular_region_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vernacular_region
    ADD CONSTRAINT vernacular_region_label_key UNIQUE (label);


--
-- Name: vernacular_region vernacular_region_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vernacular_region
    ADD CONSTRAINT vernacular_region_pkey PRIMARY KEY (vernacular_region_id);


--
-- Name: ix_edition__edition_consulted_edition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_edition__edition_consulted_edition_id ON public.edition__edition USING btree (consulted_edition_id);


--
-- Name: ix_edition__edition_edition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_edition__edition_edition_id ON public.edition__edition USING btree (edition_id);


--
-- Name: ix_edition__manuscripts_edition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_edition__manuscripts_edition_id ON public.edition__manuscripts USING btree (edition_id);


--
-- Name: ix_edition__manuscripts_manuscript_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_edition__manuscripts_manuscript_id ON public.edition__manuscripts USING btree (manuscript_id);


--
-- Name: ix_edition_identifier_per_text; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_edition_identifier_per_text ON public.edition USING btree (identifier_per_text);


--
-- Name: ix_edition_link_edition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_edition_link_edition_id ON public.edition_link USING btree (edition_id);


--
-- Name: ix_edition_text_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_edition_text_id ON public.edition USING btree (text_id);


--
-- Name: ix_manuscript_codex_identifier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_manuscript_codex_identifier ON public.manuscript USING btree (codex_identifier);


--
-- Name: ix_manuscript_identifier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_manuscript_identifier ON public.manuscript USING btree (identifier);


--
-- Name: ix_manuscript_link_manuscript_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_manuscript_link_manuscript_id ON public.manuscript_link USING btree (manuscript_id);


--
-- Name: ix_manuscript_relation_manuscript_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_manuscript_relation_manuscript_id ON public.manuscript_relation USING btree (manuscript_id);


--
-- Name: ix_manuscript_relation_related_manuscript_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_manuscript_relation_related_manuscript_id ON public.manuscript_relation USING btree (related_manuscript_id);


--
-- Name: ix_manuscript_text_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_manuscript_text_id ON public.manuscript USING btree (text_id);


--
-- Name: ix_repertory_link_repertory_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_repertory_link_repertory_id ON public.repertory_link USING btree (repertory_id);


--
-- Name: ix_repertory_link_text_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_repertory_link_text_id ON public.repertory_link USING btree (text_id);


--
-- Name: ix_text_identifier; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_text_identifier ON public.text USING btree (identifier);


--
-- Name: archdiocese archdiocese_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archdiocese
    ADD CONSTRAINT archdiocese_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.location(location_id);


--
-- Name: author author_author_milieu_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.author
    ADD CONSTRAINT author_author_milieu_id_fkey FOREIGN KEY (author_milieu_id) REFERENCES public.author_milieu(author_milieu_id);


--
-- Name: diocese diocese_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diocese
    ADD CONSTRAINT diocese_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.location(location_id);


--
-- Name: edition__edition edition__edition_consulted_edition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition__edition
    ADD CONSTRAINT edition__edition_consulted_edition_id_fkey FOREIGN KEY (consulted_edition_id) REFERENCES public.edition(edition_id);


--
-- Name: edition__edition edition__edition_edition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition__edition
    ADD CONSTRAINT edition__edition_edition_id_fkey FOREIGN KEY (edition_id) REFERENCES public.edition(edition_id);


--
-- Name: edition__manuscripts edition__manuscripts_edition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition__manuscripts
    ADD CONSTRAINT edition__manuscripts_edition_id_fkey FOREIGN KEY (edition_id) REFERENCES public.edition(edition_id);


--
-- Name: edition__manuscripts edition__manuscripts_manuscript_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition__manuscripts
    ADD CONSTRAINT edition__manuscripts_manuscript_id_fkey FOREIGN KEY (manuscript_id) REFERENCES public.manuscript(manuscript_id);


--
-- Name: edition_link edition_link_edition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition_link
    ADD CONSTRAINT edition_link_edition_id_fkey FOREIGN KEY (edition_id) REFERENCES public.edition(edition_id);


--
-- Name: edition_link edition_link_edition_link_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition_link
    ADD CONSTRAINT edition_link_edition_link_type_id_fkey FOREIGN KEY (edition_link_type_id) REFERENCES public.edition_link_type(edition_link_type_id);


--
-- Name: edition edition_reprint_of_edition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition
    ADD CONSTRAINT edition_reprint_of_edition_id_fkey FOREIGN KEY (reprint_of_edition_id) REFERENCES public.edition(edition_id);


--
-- Name: edition edition_text_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edition
    ADD CONSTRAINT edition_text_id_fkey FOREIGN KEY (text_id) REFERENCES public.text(text_id);


--
-- Name: institution institution_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.institution
    ADD CONSTRAINT institution_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.location(location_id);


--
-- Name: manuscript manuscript_dating_confidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_dating_confidence_id_fkey FOREIGN KEY (dating_confidence_id) REFERENCES public.dating_confidence(dating_confidence_id);


--
-- Name: manuscript_link manuscript_link_manuscript_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_link
    ADD CONSTRAINT manuscript_link_manuscript_id_fkey FOREIGN KEY (manuscript_id) REFERENCES public.manuscript(manuscript_id);


--
-- Name: manuscript_link manuscript_link_manuscript_link_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_link
    ADD CONSTRAINT manuscript_link_manuscript_link_type_id_fkey FOREIGN KEY (manuscript_link_type_id) REFERENCES public.manuscript_link_type(manuscript_link_type_id);


--
-- Name: manuscript manuscript_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.location(location_id);


--
-- Name: manuscript manuscript_manuscript_holding_institution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_manuscript_holding_institution_id_fkey FOREIGN KEY (manuscript_holding_institution_id) REFERENCES public.manuscript_holding_institution(manuscript_holding_institution_id);


--
-- Name: manuscript manuscript_manuscript_preservation_status_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_manuscript_preservation_status_id_fkey FOREIGN KEY (manuscript_preservation_status_id) REFERENCES public.manuscript_preservation_status(manuscript_preservation_status_id);


--
-- Name: manuscript manuscript_manuscript_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_manuscript_type_id_fkey FOREIGN KEY (manuscript_type_id) REFERENCES public.manuscript_type(manuscript_type_id);


--
-- Name: manuscript manuscript_origin_archdiocese_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_origin_archdiocese_id_fkey FOREIGN KEY (origin_archdiocese_id) REFERENCES public.archdiocese(archdiocese_id);


--
-- Name: manuscript manuscript_origin_diocese_confidence_rating_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_origin_diocese_confidence_rating_id_fkey FOREIGN KEY (origin_diocese_confidence_rating_id) REFERENCES public.origin_confidence(origin_confidence_id);


--
-- Name: manuscript manuscript_origin_diocese_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_origin_diocese_id_fkey FOREIGN KEY (origin_diocese_id) REFERENCES public.diocese(diocese_id);


--
-- Name: manuscript manuscript_origin_institution_confidence_rating_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_origin_institution_confidence_rating_id_fkey FOREIGN KEY (origin_institution_confidence_rating_id) REFERENCES public.origin_confidence(origin_confidence_id);


--
-- Name: manuscript manuscript_origin_institution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_origin_institution_id_fkey FOREIGN KEY (origin_institution_id) REFERENCES public.institution(institution_id);


--
-- Name: manuscript manuscript_provenance_early_confidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_provenance_early_confidence_id_fkey FOREIGN KEY (provenance_early_confidence_id) REFERENCES public.provenance_confidence(provenance_confidence_id);


--
-- Name: manuscript manuscript_provenance_early_institute_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_provenance_early_institute_id_fkey FOREIGN KEY (provenance_early_institute_id) REFERENCES public.institution(institution_id);


--
-- Name: manuscript manuscript_provenance_later_confidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_provenance_later_confidence_id_fkey FOREIGN KEY (provenance_later_confidence_id) REFERENCES public.provenance_confidence(provenance_confidence_id);


--
-- Name: manuscript manuscript_provenance_later_institute_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_provenance_later_institute_id_fkey FOREIGN KEY (provenance_later_institute_id) REFERENCES public.institution(institution_id);


--
-- Name: manuscript_relation manuscript_relation_manuscript_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_relation
    ADD CONSTRAINT manuscript_relation_manuscript_id_fkey FOREIGN KEY (manuscript_id) REFERENCES public.manuscript(manuscript_id);


--
-- Name: manuscript_relation manuscript_relation_manuscript_relationship_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_relation
    ADD CONSTRAINT manuscript_relation_manuscript_relationship_type_id_fkey FOREIGN KEY (manuscript_relationship_type_id) REFERENCES public.manuscript_relationship_type(manuscript_relationship_type_id);


--
-- Name: manuscript_relation manuscript_relation_related_manuscript_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript_relation
    ADD CONSTRAINT manuscript_relation_related_manuscript_id_fkey FOREIGN KEY (related_manuscript_id) REFERENCES public.manuscript(manuscript_id);


--
-- Name: manuscript manuscript_text_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_text_id_fkey FOREIGN KEY (text_id) REFERENCES public.text(text_id);


--
-- Name: manuscript manuscript_vernacular_region_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manuscript
    ADD CONSTRAINT manuscript_vernacular_region_id_fkey FOREIGN KEY (vernacular_region_id) REFERENCES public.vernacular_region(vernacular_region_id);


--
-- Name: repertory_link repertory_link_repertory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repertory_link
    ADD CONSTRAINT repertory_link_repertory_id_fkey FOREIGN KEY (repertory_id) REFERENCES public.repertory(repertory_id);


--
-- Name: repertory_link repertory_link_text_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repertory_link
    ADD CONSTRAINT repertory_link_text_id_fkey FOREIGN KEY (text_id) REFERENCES public.text(text_id);


--
-- Name: text text_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.author(author_id);


--
-- Name: text text_creation_archdiocese_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_creation_archdiocese_id_fkey FOREIGN KEY (creation_archdiocese_id) REFERENCES public.archdiocese(archdiocese_id);


--
-- Name: text text_creation_diocese_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_creation_diocese_id_fkey FOREIGN KEY (creation_diocese_id) REFERENCES public.diocese(diocese_id);


--
-- Name: text text_creation_institution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_creation_institution_id_fkey FOREIGN KEY (creation_institution_id) REFERENCES public.institution(institution_id);


--
-- Name: text text_dating_confidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_dating_confidence_id_fkey FOREIGN KEY (dating_confidence_id) REFERENCES public.dating_confidence(dating_confidence_id);


--
-- Name: text text_destinary_archdiocese_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_destinary_archdiocese_id_fkey FOREIGN KEY (destinary_archdiocese_id) REFERENCES public.archdiocese(archdiocese_id);


--
-- Name: text text_destinary_diocese_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_destinary_diocese_id_fkey FOREIGN KEY (destinary_diocese_id) REFERENCES public.diocese(diocese_id);


--
-- Name: text text_destinary_institution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_destinary_institution_id_fkey FOREIGN KEY (destinary_institution_id) REFERENCES public.institution(institution_id);


--
-- Name: text text_reecriture_text_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_reecriture_text_id_fkey FOREIGN KEY (reecriture_text_id) REFERENCES public.text(text_id);


--
-- Name: text text_text_form_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_text_form_id_fkey FOREIGN KEY (text_form_id) REFERENCES public.text_form(text_form_id);


--
-- Name: text text_text_source_subtype_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_text_source_subtype_id_fkey FOREIGN KEY (text_source_subtype_id) REFERENCES public.text_source_subtype(text_source_subtype_id);


--
-- Name: text text_text_source_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text
    ADD CONSTRAINT text_text_source_type_id_fkey FOREIGN KEY (text_source_type_id) REFERENCES public.text_source_type(text_source_type_id);


--
--


