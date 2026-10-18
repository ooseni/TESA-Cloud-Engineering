-- The system of record, as far as the demo needs it: one row per payment, the latest version only.
CREATE TABLE IF NOT EXISTS payments (
    payment_id uuid        PRIMARY KEY,
    channel    text        NOT NULL,
    reference  text        NOT NULL,
    product    text        NOT NULL,
    customer   text        NOT NULL,
    amount     bigint      NOT NULL CHECK (amount > 0),
    status     text        NOT NULL CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED', 'UNKNOWN', 'REVIEW')),
    version    integer     NOT NULL CHECK (version > 0),
    token      text,
    reason     text,
    updated_at timestamptz NOT NULL,
    UNIQUE (channel, reference)              -- catches a reference reused after the 48-hour window
);

-- Payments that could not be recorded as they arrived, for reconciliation.
CREATE TABLE IF NOT EXISTS flags (
    payment_id uuid        PRIMARY KEY,
    channel    text        NOT NULL,
    reference  text        NOT NULL,
    reason     text        NOT NULL,
    flagged_at timestamptz NOT NULL DEFAULT now()
);
