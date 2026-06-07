--
-- PostgreSQL database dump
--

\restrict cinq0p8OmIEbSVdrUResxmVmGGQ1dIFIjuu4PVVEERLJJSlAZglbiGTeePFDul5

-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: sales_plan; Type: TABLE; Schema: public; Owner: ozonuser
--

CREATE TABLE public.sales_plan (
    id integer NOT NULL,
    company_id integer NOT NULL,
    scope_type character varying NOT NULL,
    scope_ref character varying,
    metric_code character varying NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    analysis_start date,
    analysis_end date,
    base_forecast numeric,
    target_value numeric,
    distribution_mode character varying NOT NULL,
    source_pref character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    note text,
    source character varying DEFAULT 'user'::character varying NOT NULL,
    CONSTRAINT ck_sales_plan_ck_sales_plan_distribution_mode CHECK (((distribution_mode)::text = ANY ((ARRAY['proportional'::character varying, 'manual'::character varying, 'seasonal'::character varying])::text[]))),
    CONSTRAINT ck_sales_plan_ck_sales_plan_scope_type CHECK (((scope_type)::text = ANY ((ARRAY['company'::character varying, 'cabinet'::character varying, 'category'::character varying, 'group'::character varying, 'glue'::character varying, 'sku'::character varying])::text[]))),
    CONSTRAINT ck_sales_plan_ck_sales_plan_source_pref CHECK (((source_pref)::text = ANY ((ARRAY['operational'::character varying, 'official'::character varying])::text[])))
);


ALTER TABLE public.sales_plan OWNER TO ozonuser;

--
-- Name: sales_plan_id_seq; Type: SEQUENCE; Schema: public; Owner: ozonuser
--

CREATE SEQUENCE public.sales_plan_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sales_plan_id_seq OWNER TO ozonuser;

--
-- Name: sales_plan_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ozonuser
--

ALTER SEQUENCE public.sales_plan_id_seq OWNED BY public.sales_plan.id;


--
-- Name: sales_plan id; Type: DEFAULT; Schema: public; Owner: ozonuser
--

ALTER TABLE ONLY public.sales_plan ALTER COLUMN id SET DEFAULT nextval('public.sales_plan_id_seq'::regclass);


--
-- Data for Name: sales_plan; Type: TABLE DATA; Schema: public; Owner: ozonuser
--

COPY public.sales_plan (id, company_id, scope_type, scope_ref, metric_code, period_start, period_end, analysis_start, analysis_end, base_forecast, target_value, distribution_mode, source_pref, created_at, updated_at, note, source) FROM stdin;
\.


--
-- Name: sales_plan_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ozonuser
--

SELECT pg_catalog.setval('public.sales_plan_id_seq', 1, false);


--
-- Name: sales_plan pk_sales_plan; Type: CONSTRAINT; Schema: public; Owner: ozonuser
--

ALTER TABLE ONLY public.sales_plan
    ADD CONSTRAINT pk_sales_plan PRIMARY KEY (id);


--
-- PostgreSQL database dump complete
--

\unrestrict cinq0p8OmIEbSVdrUResxmVmGGQ1dIFIjuu4PVVEERLJJSlAZglbiGTeePFDul5

