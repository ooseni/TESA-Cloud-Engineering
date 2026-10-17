-- A least-privilege login for the application, instead of the master user.
-- The password arrives as the sqlcmd variable APP_PASSWORD (from AWS Secrets Manager on RDS); it is never
-- stored in this file. Safe to run again: the password is reset and nothing is duplicated.
USE master;
GO

IF SUSER_ID(N'squad_app') IS NULL
    CREATE LOGIN squad_app WITH PASSWORD = N'$(APP_PASSWORD)', CHECK_POLICY = ON, DEFAULT_DATABASE = squad_planner;
ELSE
    ALTER LOGIN squad_app WITH PASSWORD = N'$(APP_PASSWORD)';
GO

USE squad_planner;
GO

IF USER_ID(N'squad_app') IS NULL
    CREATE USER squad_app FOR LOGIN squad_app WITH DEFAULT_SCHEMA = fantasy;
GO

IF DATABASE_PRINCIPAL_ID(N'squad_writer') IS NULL
    CREATE ROLE squad_writer;
GO

-- Read, add and update players; no DELETE, and no right to change the schema.
GRANT SELECT, INSERT, UPDATE ON SCHEMA::fantasy TO squad_writer;
GO

IF IS_ROLEMEMBER(N'squad_writer', N'squad_app') = 0
    ALTER ROLE squad_writer ADD MEMBER squad_app;
GO
