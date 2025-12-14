-- P26-P28 缺失表创建脚本

-- 创建枚举类型（如果不存在）
DO $$ BEGIN
    CREATE TYPE alert_status AS ENUM ('firing', 'resolved');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 创建 alerts_events 表
CREATE TABLE IF NOT EXISTS alerts_events (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    site_id VARCHAR(64),
    alert_code VARCHAR(128) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    status alert_status NOT NULL DEFAULT 'firing',
    "window" VARCHAR(16) NOT NULL DEFAULT '15m',
    current_value FLOAT,
    threshold FLOAT,
    condition VARCHAR(16),
    unit VARCHAR(32),
    dedup_key VARCHAR(256) NOT NULL,
    first_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP,
    context JSONB NOT NULL DEFAULT '{}',
    webhook_sent VARCHAR(16),
    webhook_sent_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_alerts_events_tenant_id ON alerts_events(tenant_id);
CREATE INDEX IF NOT EXISTS ix_alerts_events_site_id ON alerts_events(site_id);
CREATE INDEX IF NOT EXISTS ix_alerts_events_alert_code ON alerts_events(alert_code);
CREATE INDEX IF NOT EXISTS ix_alerts_events_severity ON alerts_events(severity);
CREATE INDEX IF NOT EXISTS ix_alerts_events_status ON alerts_events(status);
CREATE INDEX IF NOT EXISTS ix_alerts_events_dedup_key ON alerts_events(dedup_key);
CREATE INDEX IF NOT EXISTS ix_alerts_events_tenant_status ON alerts_events(tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_alerts_events_dedup_status ON alerts_events(dedup_key, status);
CREATE INDEX IF NOT EXISTS ix_alerts_events_first_seen ON alerts_events(first_seen_at);

-- 创建 alerts_silences 表
CREATE TABLE IF NOT EXISTS alerts_silences (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    site_id VARCHAR(64),
    alert_code VARCHAR(128),
    severity VARCHAR(32),
    starts_at TIMESTAMP NOT NULL DEFAULT NOW(),
    ends_at TIMESTAMP NOT NULL,
    reason TEXT,
    created_by VARCHAR(128) NOT NULL DEFAULT 'admin_console',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_alerts_silences_tenant_id ON alerts_silences(tenant_id);
CREATE INDEX IF NOT EXISTS ix_alerts_silences_site_id ON alerts_silences(site_id);
CREATE INDEX IF NOT EXISTS ix_alerts_silences_alert_code ON alerts_silences(alert_code);
CREATE INDEX IF NOT EXISTS ix_alerts_silences_severity ON alerts_silences(severity);
CREATE INDEX IF NOT EXISTS ix_alerts_silences_tenant_active ON alerts_silences(tenant_id, starts_at, ends_at);

-- 创建 releases 表
CREATE TABLE IF NOT EXISTS releases (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    site_id VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL,
    payload JSONB NOT NULL,
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    activated_at TIMESTAMP,
    archived_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_releases_tenant_id ON releases(tenant_id);
CREATE INDEX IF NOT EXISTS ix_releases_site_id ON releases(site_id);
CREATE INDEX IF NOT EXISTS ix_releases_status ON releases(status);
CREATE INDEX IF NOT EXISTS ix_releases_created_at ON releases(created_at);
CREATE INDEX IF NOT EXISTS ix_releases_tenant_site_status ON releases(tenant_id, site_id, status);

-- 创建 release_history 表
CREATE TABLE IF NOT EXISTS release_history (
    id VARCHAR(36) PRIMARY KEY,
    release_id VARCHAR(36) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    site_id VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    previous_release_id VARCHAR(36),
    operator VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_release_history_release_id ON release_history(release_id);
CREATE INDEX IF NOT EXISTS ix_release_history_tenant_id ON release_history(tenant_id);
CREATE INDEX IF NOT EXISTS ix_release_history_site_id ON release_history(site_id);
CREATE INDEX IF NOT EXISTS ix_release_history_created_at ON release_history(created_at);

-- 创建 admin_audit_log 表
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(100),
    actor VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(100) NOT NULL,
    target_id VARCHAR(255),
    payload JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_admin_audit_log_tenant_id ON admin_audit_log(tenant_id);
CREATE INDEX IF NOT EXISTS ix_admin_audit_log_actor ON admin_audit_log(actor);
CREATE INDEX IF NOT EXISTS ix_admin_audit_log_action ON admin_audit_log(action);
CREATE INDEX IF NOT EXISTS ix_admin_audit_log_created_at ON admin_audit_log(created_at);

-- 创建 policies 表
CREATE TABLE IF NOT EXISTS policies (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    policy_type VARCHAR(100) NOT NULL,
    version VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMP,
    UNIQUE(tenant_id, policy_type, version)
);

CREATE INDEX IF NOT EXISTS ix_policies_tenant_id ON policies(tenant_id);
CREATE INDEX IF NOT EXISTS ix_policies_policy_type ON policies(policy_type);
CREATE INDEX IF NOT EXISTS ix_policies_is_active ON policies(is_active);

-- 添加 release_id 到 trace_ledger（如果不存在）
DO $$ BEGIN
    ALTER TABLE trace_ledger ADD COLUMN release_id UUID;
EXCEPTION
    WHEN duplicate_column THEN null;
END $$;

CREATE INDEX IF NOT EXISTS ix_trace_ledger_release_id ON trace_ledger(release_id);
