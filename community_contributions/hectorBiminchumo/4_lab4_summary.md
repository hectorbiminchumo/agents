# Week 6 Day 4: Autonomous Traders (`6_mcp/4_lab4.ipynb`)

My notes on how the lab works, written so I can reread them later.

## The idea

A small simulated trading company run by AI agents: **four traders** and **one researcher**. The money is simulated, and prices can come from real market data (Massive). It is a demo of agents that use MCP servers as tools.

## The cast

| Piece | What it is |
|---|---|
| Traders: Warren, George, Ray, Cathie | Agents with different strategies (value, macro, diversified, crypto ETFs). The strategy texts live in `backend/reset.py`. |
| Researcher | An agent each trader calls **as a tool** (`researcher.as_tool(...)`). |
| 6 MCP servers, 17 tools | **Trader:** Accounts (5 tools), Push notification (1), Market data (3). **Researcher:** Fetch (1), Tavily search only (1), Memory (6). |
| `accounts.db` | The database that connects everything: accounts, trades and logs. |

```
Trader (x4)  --asks-->  Researcher
 |- Accounts             |- Fetch    (reads a web page)
 |- Push notification    |- Tavily   (web search, filtered to one tool)
 |- Market data          |- Memory   (knowledge graph, one file per trader)
```

## The notebook, cell by cell

1. **Setup (cells 4-7):** imports, a PATH fix for the kernel, and the Windows stderr patch.
2. **Tour (cells 8-14):** `get_share_price("AAPL")`, Warren's account (balance, strategy), and a count of the 6 servers and their tools.
3. **Researcher (cells 15-19):** run it alone on "What's the latest news on Amazon?", then wrap it as a tool.
4. **Trader (cells 20-23):** register `LogTracer`, create `Trader("Warren", ...)`, `await warren.run()`, then read the last transaction back.
5. **Team (cells 24-27):** the engine loop and the dashboard, run from the terminal.

## How one trader run works (`Trader.run()` in `backend/traders.py`)

1. `Trader("Warren", ...)` only stores the names and the model. **No agent exists yet.**
2. `run()` starts the trader's 3 servers and the researcher's 3 servers.
3. It builds the **Researcher** and wraps it as a tool, then builds the **trader agent** with its instructions, that tool and its servers.
4. It reads Warren's **account and strategy** from the Accounts server's *resources* (read-only data).
5. It sends a message made by `trade_message(...)`: strategy, account, time, and the order "research, decide, trade".
6. The agent loops (max 30 turns): calls the Researcher, checks prices, buys or sells, and may change its own strategy.
7. At the end it sends a **push notification** and replies with a 2-3 sentence appraisal.
8. `do_trade` flips, so the next run is a **rebalance** run instead of a trade run.

## Ideas to remember

- **Account vs agent.** `Account.get("Warren")` is *data* (get-or-create a database row). The agent is built fresh at every run, and Warren's identity persists because it is read from the database. In the notebook the variable `warren` is an `Account` in cell 12 and a `Trader` in cell 21.
- **Tool vs resource.** A tool *does* something (`buy_shares`). A resource *gives* data (`accounts://strategy/{name}`).
- **Agent as a tool vs handoff.** With a tool, the trader stays in control and gets an answer back. A handoff passes the whole conversation away.
- **Tool filtering.** Tavily is limited to `tavily_search`. Fewer tools mean a more focused agent, which is context engineering.
- **Separate memory per trader.** The Memory server writes to `memory/<name>.db`.
- **Tracing.** `LogTracer` writes each step into the database, and the dashboard shows it.

## Running the whole team

```bash
cd 6_mcp
uv run app.py                      # terminal 1: the dashboard
uv run -m backend.trading_floor    # terminal 2: the engine loop
```

The loop runs all four traders at once with `asyncio.gather` every `RUN_EVERY_N_MINUTES` (default 60) and skips closed-market hours. The two programs share only the database.

| `.env` setting | What it does | Default |
|---|---|---|
| `RUN_EVERY_N_MINUTES` | How often the team runs | 60 |
| `RUN_EVEN_WHEN_MARKET_IS_CLOSED` | Trade out of market hours | false |
| `USE_MANY_MODELS` | A different model per trader (GPT 5.5, DeepSeek V4, Gemini 3.5 Flash, Grok 4.3) | false |

## Gotchas

- **Cost:** every trader run makes many model, Tavily and push calls, and the loop repeats. Stop it with Ctrl+C.
- **Kernel PATH:** `FileNotFoundError: 'uv'` or `'npx'` means the notebook kernel has a short `PATH`. Run the PATH cell (cell 5), or start Cursor from a terminal with `cursor .`. After a kernel restart, run cells 4, 5 and 7 again before any cell that starts a server.
- **Empty strategy:** if cell 12 prints no strategy, run `reset_traders()` once. It resets all four accounts.

## One sentence

A loop that starts MCP servers, builds an agent from the database state, lets it use tools, and writes the results back to the database.
