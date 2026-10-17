-- The target squad table, with the rules the data must follow enforced by the database itself.
-- Safe to run again: every object is created only if it is missing.
USE squad_planner;
GO

IF SCHEMA_ID(N'fantasy') IS NULL
    EXEC (N'CREATE SCHEMA fantasy AUTHORIZATION dbo;');
GO

IF OBJECT_ID(N'fantasy.target_squad', N'U') IS NULL
BEGIN
    CREATE TABLE fantasy.target_squad (
        player_id      INT IDENTITY(1, 1) NOT NULL
            CONSTRAINT pk_target_squad PRIMARY KEY,
        player_name    NVARCHAR(100) NOT NULL,          -- NVARCHAR: names such as Ødegaard keep their letters
        position       VARCHAR(10)   NOT NULL
            CONSTRAINT ck_target_squad_position CHECK (position IN ('Goalkeeper', 'Defender', 'Midfielder', 'Forward')),
        club           NVARCHAR(50)  NOT NULL,
        price_millions DECIMAL(4, 1) NOT NULL
            CONSTRAINT ck_target_squad_price CHECK (price_millions BETWEEN 3.5 AND 20.0),
        total_points   INT           NOT NULL
            CONSTRAINT df_target_squad_points DEFAULT (0)
            CONSTRAINT ck_target_squad_points CHECK (total_points >= 0),
        added_at       DATETIME2(0)  NOT NULL
            CONSTRAINT df_target_squad_added_at DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT uq_target_squad_player UNIQUE (player_name, club)
    );
END;
GO
