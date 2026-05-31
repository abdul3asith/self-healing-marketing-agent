"""
UPSTREAM TREND SELECTION  —  scrape current trends, compare to OUR data, pick the best.

This is the stage the contracts call "upstream" (core/contracts.py): the worker never
scrapes or ranks; it just gets a Trend. This package produces those Trends for the
LIVE worker.

CRITICAL GOTCHA (README): this feeds the running worker ONLY. It must NEVER touch the
frozen eval set in eval/trends.py — that set is the deterministic yardstick the Daytona
sandbox grades fixes against, and a live/non-deterministic eval set would destroy the
proof-of-fix. Same Trend schema, different jobs.
"""
