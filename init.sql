--
-- PostgreSQL database dump
--

\restrict 5gquQUPXNm5HeclWNdWb23KhR32KBZCakWOn7bLRZa1dwLbeGTVBel4awbAHfyU

-- Dumped from database version 16.13 (Homebrew)
-- Dumped by pg_dump version 16.13 (Homebrew)

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
-- Name: dm_logs; Type: TABLE; Schema: public; Owner: node
--

CREATE TABLE public.dm_logs (
    id integer NOT NULL,
    kol_id integer,
    platform text,
    direction text DEFAULT 'outbound'::text,
    content text,
    status text DEFAULT 'pending'::text,
    sent_at timestamp without time zone,
    replied_at timestamp without time zone,
    reply_content text
);


ALTER TABLE public.dm_logs OWNER TO node;

--
-- Name: dm_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: node
--

CREATE SEQUENCE public.dm_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.dm_logs_id_seq OWNER TO node;

--
-- Name: dm_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: node
--

ALTER SEQUENCE public.dm_logs_id_seq OWNED BY public.dm_logs.id;


--
-- Name: kol_metrics; Type: TABLE; Schema: public; Owner: node
--

CREATE TABLE public.kol_metrics (
    id integer NOT NULL,
    kol_id integer,
    platform text DEFAULT 'linkedin'::text,
    followers_count integer,
    connections_count integer,
    posts_count integer,
    engagement_rate double precision,
    captured_at timestamp without time zone DEFAULT now(),
    following_count integer
);


ALTER TABLE public.kol_metrics OWNER TO node;

--
-- Name: kol_metrics_id_seq; Type: SEQUENCE; Schema: public; Owner: node
--

CREATE SEQUENCE public.kol_metrics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.kol_metrics_id_seq OWNER TO node;

--
-- Name: kol_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: node
--

ALTER SEQUENCE public.kol_metrics_id_seq OWNED BY public.kol_metrics.id;


--
-- Name: kols; Type: TABLE; Schema: public; Owner: node
--

CREATE TABLE public.kols (
    id integer NOT NULL,
    name text NOT NULL,
    org text,
    category text,
    linkedin_url text,
    linkedin_id text,
    twitter_url text,
    twitter_id text,
    notes text,
    status text DEFAULT 'active'::text,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    dm_text text,
    dm_day text,
    dm_time text
);


ALTER TABLE public.kols OWNER TO node;

--
-- Name: kols_id_seq; Type: SEQUENCE; Schema: public; Owner: node
--

CREATE SEQUENCE public.kols_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.kols_id_seq OWNER TO node;

--
-- Name: kols_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: node
--

ALTER SEQUENCE public.kols_id_seq OWNED BY public.kols.id;


--
-- Name: linkedin_connections; Type: TABLE; Schema: public; Owner: node
--

CREATE TABLE public.linkedin_connections (
    id integer NOT NULL,
    kol_id integer,
    connection_name text,
    connection_url text,
    connection_title text,
    direction text,
    change_type text DEFAULT 'existing'::text,
    detected_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.linkedin_connections OWNER TO node;

--
-- Name: linkedin_connections_id_seq; Type: SEQUENCE; Schema: public; Owner: node
--

CREATE SEQUENCE public.linkedin_connections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.linkedin_connections_id_seq OWNER TO node;

--
-- Name: linkedin_connections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: node
--

ALTER SEQUENCE public.linkedin_connections_id_seq OWNED BY public.linkedin_connections.id;


--
-- Name: linkedin_interactions; Type: TABLE; Schema: public; Owner: node
--

CREATE TABLE public.linkedin_interactions (
    id integer NOT NULL,
    kol_id integer,
    target_name text,
    target_url text,
    interaction_type text,
    content text,
    post_url text,
    captured_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.linkedin_interactions OWNER TO node;

--
-- Name: linkedin_interactions_id_seq; Type: SEQUENCE; Schema: public; Owner: node
--

CREATE SEQUENCE public.linkedin_interactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.linkedin_interactions_id_seq OWNER TO node;

--
-- Name: linkedin_interactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: node
--

ALTER SEQUENCE public.linkedin_interactions_id_seq OWNED BY public.linkedin_interactions.id;


--
-- Name: linkedin_posts; Type: TABLE; Schema: public; Owner: node
--

CREATE TABLE public.linkedin_posts (
    id integer NOT NULL,
    kol_id integer,
    post_id text,
    content text,
    likes integer DEFAULT 0,
    comments integer DEFAULT 0,
    reposts integer DEFAULT 0,
    post_url text,
    posted_at timestamp without time zone,
    captured_at timestamp without time zone DEFAULT now(),
    is_notified boolean DEFAULT false
);


ALTER TABLE public.linkedin_posts OWNER TO node;

--
-- Name: linkedin_posts_id_seq; Type: SEQUENCE; Schema: public; Owner: node
--

CREATE SEQUENCE public.linkedin_posts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.linkedin_posts_id_seq OWNER TO node;

--
-- Name: linkedin_posts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: node
--

ALTER SEQUENCE public.linkedin_posts_id_seq OWNED BY public.linkedin_posts.id;


--
-- Name: twitter_post_replies; Type: TABLE; Schema: public; Owner: node
--

CREATE TABLE public.twitter_post_replies (
    id integer NOT NULL,
    post_id integer,
    username text NOT NULL,
    captured_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.twitter_post_replies OWNER TO node;

--
-- Name: twitter_post_replies_id_seq; Type: SEQUENCE; Schema: public; Owner: node
--

CREATE SEQUENCE public.twitter_post_replies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.twitter_post_replies_id_seq OWNER TO node;

--
-- Name: twitter_post_replies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: node
--

ALTER SEQUENCE public.twitter_post_replies_id_seq OWNED BY public.twitter_post_replies.id;


--
-- Name: twitter_post_reposts; Type: TABLE; Schema: public; Owner: node
--

CREATE TABLE public.twitter_post_reposts (
    id integer NOT NULL,
    post_id integer,
    username text NOT NULL,
    captured_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.twitter_post_reposts OWNER TO node;

--
-- Name: twitter_post_reposts_id_seq; Type: SEQUENCE; Schema: public; Owner: node
--

CREATE SEQUENCE public.twitter_post_reposts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.twitter_post_reposts_id_seq OWNER TO node;

--
-- Name: twitter_post_reposts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: node
--

ALTER SEQUENCE public.twitter_post_reposts_id_seq OWNED BY public.twitter_post_reposts.id;


--
-- Name: twitter_posts; Type: TABLE; Schema: public; Owner: node
--

CREATE TABLE public.twitter_posts (
    id integer DEFAULT nextval('public.linkedin_posts_id_seq'::regclass) NOT NULL,
    kol_id integer,
    post_id text,
    content text,
    likes integer,
    comments integer,
    reposts integer,
    post_url text,
    posted_at timestamp without time zone,
    captured_at timestamp without time zone,
    is_notified boolean DEFAULT false,
    views integer DEFAULT 0,
    bookmarks integer DEFAULT 0,
    last_likes integer DEFAULT 0,
    last_views integer DEFAULT 0,
    last_reposts integer DEFAULT 0,
    last_bookmarks integer DEFAULT 0,
    last_comments integer DEFAULT 0
);


ALTER TABLE public.twitter_posts OWNER TO node;

--
-- Name: dm_logs id; Type: DEFAULT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.dm_logs ALTER COLUMN id SET DEFAULT nextval('public.dm_logs_id_seq'::regclass);


--
-- Name: kol_metrics id; Type: DEFAULT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.kol_metrics ALTER COLUMN id SET DEFAULT nextval('public.kol_metrics_id_seq'::regclass);


--
-- Name: kols id; Type: DEFAULT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.kols ALTER COLUMN id SET DEFAULT nextval('public.kols_id_seq'::regclass);


--
-- Name: linkedin_connections id; Type: DEFAULT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.linkedin_connections ALTER COLUMN id SET DEFAULT nextval('public.linkedin_connections_id_seq'::regclass);


--
-- Name: linkedin_interactions id; Type: DEFAULT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.linkedin_interactions ALTER COLUMN id SET DEFAULT nextval('public.linkedin_interactions_id_seq'::regclass);


--
-- Name: linkedin_posts id; Type: DEFAULT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.linkedin_posts ALTER COLUMN id SET DEFAULT nextval('public.linkedin_posts_id_seq'::regclass);


--
-- Name: twitter_post_replies id; Type: DEFAULT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.twitter_post_replies ALTER COLUMN id SET DEFAULT nextval('public.twitter_post_replies_id_seq'::regclass);


--
-- Name: twitter_post_reposts id; Type: DEFAULT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.twitter_post_reposts ALTER COLUMN id SET DEFAULT nextval('public.twitter_post_reposts_id_seq'::regclass);


--
-- Name: dm_logs dm_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.dm_logs
    ADD CONSTRAINT dm_logs_pkey PRIMARY KEY (id);


--
-- Name: kol_metrics kol_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.kol_metrics
    ADD CONSTRAINT kol_metrics_pkey PRIMARY KEY (id);


--
-- Name: kols kols_pkey; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.kols
    ADD CONSTRAINT kols_pkey PRIMARY KEY (id);


--
-- Name: linkedin_connections linkedin_connections_pkey; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.linkedin_connections
    ADD CONSTRAINT linkedin_connections_pkey PRIMARY KEY (id);


--
-- Name: linkedin_interactions linkedin_interactions_pkey; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.linkedin_interactions
    ADD CONSTRAINT linkedin_interactions_pkey PRIMARY KEY (id);


--
-- Name: linkedin_posts linkedin_posts_pkey; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.linkedin_posts
    ADD CONSTRAINT linkedin_posts_pkey PRIMARY KEY (id);


--
-- Name: linkedin_posts linkedin_posts_post_id_key; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.linkedin_posts
    ADD CONSTRAINT linkedin_posts_post_id_key UNIQUE (post_id);


--
-- Name: twitter_post_replies twitter_post_replies_pkey; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.twitter_post_replies
    ADD CONSTRAINT twitter_post_replies_pkey PRIMARY KEY (id);


--
-- Name: twitter_post_replies twitter_post_replies_post_id_username_key; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.twitter_post_replies
    ADD CONSTRAINT twitter_post_replies_post_id_username_key UNIQUE (post_id, username);


--
-- Name: twitter_post_reposts twitter_post_reposts_pkey; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.twitter_post_reposts
    ADD CONSTRAINT twitter_post_reposts_pkey PRIMARY KEY (id);


--
-- Name: twitter_post_reposts twitter_post_reposts_post_id_username_key; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.twitter_post_reposts
    ADD CONSTRAINT twitter_post_reposts_post_id_username_key UNIQUE (post_id, username);


--
-- Name: twitter_posts twitter_posts_pkey; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.twitter_posts
    ADD CONSTRAINT twitter_posts_pkey PRIMARY KEY (id);


--
-- Name: twitter_posts twitter_posts_post_id_key; Type: CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.twitter_posts
    ADD CONSTRAINT twitter_posts_post_id_key UNIQUE (post_id);


--
-- Name: idx_kol_metrics_captured; Type: INDEX; Schema: public; Owner: node
--

CREATE INDEX idx_kol_metrics_captured ON public.kol_metrics USING btree (captured_at);


--
-- Name: idx_linkedin_posts_captured; Type: INDEX; Schema: public; Owner: node
--

CREATE INDEX idx_linkedin_posts_captured ON public.linkedin_posts USING btree (captured_at);


--
-- Name: idx_linkedin_posts_kol; Type: INDEX; Schema: public; Owner: node
--

CREATE INDEX idx_linkedin_posts_kol ON public.linkedin_posts USING btree (kol_id);


--
-- Name: dm_logs dm_logs_kol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.dm_logs
    ADD CONSTRAINT dm_logs_kol_id_fkey FOREIGN KEY (kol_id) REFERENCES public.kols(id);


--
-- Name: kol_metrics kol_metrics_kol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.kol_metrics
    ADD CONSTRAINT kol_metrics_kol_id_fkey FOREIGN KEY (kol_id) REFERENCES public.kols(id);


--
-- Name: linkedin_connections linkedin_connections_kol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.linkedin_connections
    ADD CONSTRAINT linkedin_connections_kol_id_fkey FOREIGN KEY (kol_id) REFERENCES public.kols(id);


--
-- Name: linkedin_interactions linkedin_interactions_kol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.linkedin_interactions
    ADD CONSTRAINT linkedin_interactions_kol_id_fkey FOREIGN KEY (kol_id) REFERENCES public.kols(id);


--
-- Name: linkedin_posts linkedin_posts_kol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.linkedin_posts
    ADD CONSTRAINT linkedin_posts_kol_id_fkey FOREIGN KEY (kol_id) REFERENCES public.kols(id);


--
-- Name: twitter_post_replies twitter_post_replies_post_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.twitter_post_replies
    ADD CONSTRAINT twitter_post_replies_post_id_fkey FOREIGN KEY (post_id) REFERENCES public.twitter_posts(id) ON DELETE CASCADE;


--
-- Name: twitter_post_reposts twitter_post_reposts_post_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: node
--

ALTER TABLE ONLY public.twitter_post_reposts
    ADD CONSTRAINT twitter_post_reposts_post_id_fkey FOREIGN KEY (post_id) REFERENCES public.twitter_posts(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

-- Users table (required by the application)
CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT UNIQUE,
    discord_webhook_posts TEXT,
    discord_webhook_interactions TEXT,
    discord_webhook_metrics TEXT,
    discord_webhook_heatmap TEXT,
    discord_webhook_following TEXT,
    discord_webhook_followers TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE public.users OWNER TO node;

-- Add user_id column to kols if not exists
ALTER TABLE public.kols ADD COLUMN IF NOT EXISTS user_id INTEGER DEFAULT 1;

-- Default admin user
INSERT INTO public.users (id, username, password_hash, email) VALUES (1, 'admin', 'admin', 'admin@local') ON CONFLICT DO NOTHING;

\unrestrict 5gquQUPXNm5HeclWNdWb23KhR32KBZCakWOn7bLRZa1dwLbeGTVBel4awbAHfyU

