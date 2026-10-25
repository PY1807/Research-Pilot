-- Runs once, the first time the Postgres volume is created.
-- A separate database for tests, so `make test` never touches development data.
CREATE DATABASE researchpilot_test OWNER researchpilot;
