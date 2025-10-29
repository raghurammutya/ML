## Kite F&O Scripts

### Multi-account configuration

1. Copy `kite_accounts.yaml` (or point `KITE_ACCOUNTS_FILE` env var somewhere else).
2. For each account add `api_key`, `api_secret`, `username`, `password`, and `totp_key`. You can reference environment variables using the `${VAR_NAME}` syntax (see the example file).
3. Populate the environment variables in `.env` (or your shell) for each account, e.g.:
   ```
   KITE_PRIMARY_API_KEY=xxxxx
   KITE_PRIMARY_API_SECRET=yyyyy
   ...
   ```
4. By default the first account in the YAML file is used. Override per run via `KITE_ACCOUNT=<account_id>` environment variable.
5. Access tokens are saved under `Kite_FOdata_scripts/tokens/` with the naming pattern `kite_token_<account_id>.json` so that each account maintains its own session state.

### Session orchestration / load distribution

- `session_manager.SessionOrchestrator` loads every configured account via `KiteAccountManager` and exposes two main helpers:
  * `borrow()` – async context manager that locks a specific account and yields the `KiteService` instance (pre-authenticated). When the context exits it releases the lock and tracks failures to aid monitoring.
  * `distribute(work_items)` – round-robin splitter that assigns arbitrary work items (e.g., expiry dates, strike batches) across the available accounts.
- Scripts can import `SessionOrchestrator` to parallelize historical fetches or future real-time subscriptions without exceeding Kite’s per-account limits.
- Future work: plug in subscription counters to enforce the 3k-instrument cap, persist rotation metadata, and add automatic retry/resubscribe hooks for the ticker service.
