-- ============================================================
-- KOL Monitor Pro: Supabase Migration Script
-- Run this in Supabase Dashboard → SQL Editor
-- ============================================================

-- ============================================================
-- 1. CORE TABLES
-- ============================================================

-- KOL Profiles (linked to Supabase auth.users)
CREATE TABLE public.kols (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    org         TEXT,
    category    TEXT,
    linkedin_url TEXT,
    twitter_url  TEXT,
    twitter_id   TEXT,
    notes       TEXT,
    status      TEXT DEFAULT 'active',
    dm_text     TEXT,
    dm_day      TEXT,
    dm_time     TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Twitter Posts (scraped content)
CREATE TABLE public.twitter_posts (
    id           BIGSERIAL PRIMARY KEY,
    kol_id       BIGINT REFERENCES public.kols(id) ON DELETE CASCADE,
    post_id      TEXT UNIQUE,
    content      TEXT,
    likes        INT DEFAULT 0,
    comments     INT DEFAULT 0,
    reposts      INT DEFAULT 0,
    views        INT DEFAULT 0,
    bookmarks    INT DEFAULT 0,
    post_url     TEXT,
    posted_at    TIMESTAMPTZ,
    captured_at  TIMESTAMPTZ DEFAULT now(),
    is_notified  BOOLEAN DEFAULT false,
    last_likes     INT DEFAULT 0,
    last_views     INT DEFAULT 0,
    last_reposts   INT DEFAULT 0,
    last_bookmarks INT DEFAULT 0,
    last_comments  INT DEFAULT 0
);

-- KOL Metrics (follower/following count snapshots)
CREATE TABLE public.kol_metrics (
    id              BIGSERIAL PRIMARY KEY,
    kol_id          BIGINT REFERENCES public.kols(id) ON DELETE CASCADE,
    platform        TEXT DEFAULT 'twitter',
    followers_count INT,
    following_count INT,
    posts_count     INT,
    engagement_rate DOUBLE PRECISION,
    captured_at     TIMESTAMPTZ DEFAULT now()
);

-- DM Logs (audit trail for scheduled DMs)
CREATE TABLE public.dm_logs (
    id            BIGSERIAL PRIMARY KEY,
    kol_id        BIGINT REFERENCES public.kols(id) ON DELETE CASCADE,
    platform      TEXT DEFAULT 'twitter',
    direction     TEXT DEFAULT 'outbound',
    content       TEXT,
    status        TEXT DEFAULT 'pending',
    error_log     TEXT,
    sent_at       TIMESTAMPTZ,
    replied_at    TIMESTAMPTZ,
    reply_content TEXT
);

-- Twitter Post Replies (who replied to a KOL's post)
CREATE TABLE public.twitter_post_replies (
    id          BIGSERIAL PRIMARY KEY,
    post_id     BIGINT REFERENCES public.twitter_posts(id) ON DELETE CASCADE,
    username    TEXT NOT NULL,
    captured_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(post_id, username)
);

-- Twitter Post Reposts (who reposted a KOL's post)
CREATE TABLE public.twitter_post_reposts (
    id          BIGSERIAL PRIMARY KEY,
    post_id     BIGINT REFERENCES public.twitter_posts(id) ON DELETE CASCADE,
    username    TEXT NOT NULL,
    captured_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(post_id, username)
);


-- ============================================================
-- 2. USER CONFIGS (Discord Webhooks + X Session Cookies)
-- ============================================================

CREATE TABLE public.user_configs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    discord_webhook_posts        TEXT,
    discord_webhook_interactions TEXT,
    discord_webhook_heatmap      TEXT,
    discord_webhook_following    TEXT,
    discord_webhook_followers    TEXT,
    twitter_auth_token           TEXT,
    twitter_ct0                  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);


-- ============================================================
-- 3. INDEXES (for query performance)
-- ============================================================

CREATE INDEX idx_kols_user ON public.kols(user_id);
CREATE INDEX idx_kols_status ON public.kols(status);
CREATE INDEX idx_twitter_posts_kol ON public.twitter_posts(kol_id);
CREATE INDEX idx_twitter_posts_captured ON public.twitter_posts(captured_at);
CREATE INDEX idx_twitter_posts_notified ON public.twitter_posts(is_notified);
CREATE INDEX idx_kol_metrics_kol ON public.kol_metrics(kol_id);
CREATE INDEX idx_kol_metrics_captured ON public.kol_metrics(captured_at);
CREATE INDEX idx_dm_logs_kol ON public.dm_logs(kol_id);
CREATE INDEX idx_dm_logs_sent ON public.dm_logs(sent_at);


-- ============================================================
-- 4. ROW LEVEL SECURITY (RLS)
-- ============================================================

-- Enable RLS on all user-facing tables
ALTER TABLE public.kols ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.twitter_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.kol_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dm_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.twitter_post_replies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.twitter_post_reposts ENABLE ROW LEVEL SECURITY;

-- KOLs: Users can only manage their own KOLs
CREATE POLICY "kols_user_isolation"
    ON public.kols FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- User Configs: Users can only manage their own settings
CREATE POLICY "configs_user_isolation"
    ON public.user_configs FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Twitter Posts: Users can read posts belonging to their KOLs
CREATE POLICY "posts_user_read"
    ON public.twitter_posts FOR SELECT
    USING (kol_id IN (SELECT id FROM public.kols WHERE user_id = auth.uid()));

-- Insert/update for service role (scraper writes for all users)
CREATE POLICY "posts_service_write"
    ON public.twitter_posts FOR INSERT
    WITH CHECK (kol_id IN (SELECT id FROM public.kols));

CREATE POLICY "posts_service_update"
    ON public.twitter_posts FOR UPDATE
    USING (kol_id IN (SELECT id FROM public.kols));

-- KOL Metrics: Users read metrics for their KOLs
CREATE POLICY "metrics_user_read"
    ON public.kol_metrics FOR SELECT
    USING (kol_id IN (SELECT id FROM public.kols WHERE user_id = auth.uid()));

CREATE POLICY "metrics_service_write"
    ON public.kol_metrics FOR INSERT
    WITH CHECK (kol_id IN (SELECT id FROM public.kols));

-- DM Logs: Users read DM logs for their KOLs
CREATE POLICY "dm_logs_user_read"
    ON public.dm_logs FOR SELECT
    USING (kol_id IN (SELECT id FROM public.kols WHERE user_id = auth.uid()));

CREATE POLICY "dm_logs_service_write"
    ON public.dm_logs FOR INSERT
    WITH CHECK (kol_id IN (SELECT id FROM public.kols));

-- Replies: Users read replies on their KOLs' posts
CREATE POLICY "replies_user_read"
    ON public.twitter_post_replies FOR SELECT
    USING (post_id IN (
        SELECT tp.id FROM public.twitter_posts tp
        JOIN public.kols k ON tp.kol_id = k.id
        WHERE k.user_id = auth.uid()
    ));

CREATE POLICY "replies_service_write"
    ON public.twitter_post_replies FOR INSERT
    WITH CHECK (true);

-- Reposts: Users read reposts on their KOLs' posts
CREATE POLICY "reposts_user_read"
    ON public.twitter_post_reposts FOR SELECT
    USING (post_id IN (
        SELECT tp.id FROM public.twitter_posts tp
        JOIN public.kols k ON tp.kol_id = k.id
        WHERE k.user_id = auth.uid()
    ));

CREATE POLICY "reposts_service_write"
    ON public.twitter_post_reposts FOR INSERT
    WITH CHECK (true);

-- ============================================================
-- NOTE: The Railway backend uses the `service_role` key which
-- bypasses RLS entirely. This is required so the scraper and
-- scheduler can write data for ALL users in a single loop.
-- ============================================================
