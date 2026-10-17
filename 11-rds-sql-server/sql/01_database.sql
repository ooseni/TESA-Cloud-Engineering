-- Creates the database once. Safe to run again.
IF DB_ID(N'squad_planner') IS NULL
    CREATE DATABASE squad_planner;
GO
