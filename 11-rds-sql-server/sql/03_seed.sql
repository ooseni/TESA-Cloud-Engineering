-- Sample data (illustrative prices and points). MERGE makes it safe to run again:
-- existing players are updated, missing ones are added, and nothing is duplicated.
USE squad_planner;
GO

MERGE fantasy.target_squad AS target
USING (VALUES
    (N'Erling Haaland',  'Forward',    N'Man City',    14.3, 185),
    (N'Mohamed Salah',   'Midfielder', N'Liverpool',   13.1, 192),
    (N'Bukayo Saka',     'Midfielder', N'Arsenal',      9.1, 168),
    (N'William Saliba',  'Defender',   N'Arsenal',      5.8, 102),
    (N'Ollie Watkins',   'Forward',    N'Aston Villa',  8.9, 175),
    (N'Martin Ødegaard', 'Midfielder', N'Arsenal',      8.4, 150)
) AS source (player_name, position, club, price_millions, total_points)
ON target.player_name = source.player_name AND target.club = source.club
WHEN MATCHED THEN
    UPDATE SET position       = source.position,
               price_millions = source.price_millions,
               total_points   = source.total_points
WHEN NOT MATCHED BY TARGET THEN
    INSERT (player_name, position, club, price_millions, total_points)
    VALUES (source.player_name, source.position, source.club, source.price_millions, source.total_points);
GO
