-- SQLite: f2p items whose Low Alchemy payout beats ~167 gp
-- lowalch = floor(40% x value); integer division = exact floor for positives
SELECT id, name, (value * 2 / 5) AS lowalch, updated_at
FROM items
WHERE members = 0 AND lowalch > 167
ORDER BY lowalch DESC;
