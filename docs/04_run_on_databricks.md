# Run the project on Databricks (Free Edition)

Expected time: about 1.5 hours the first time. Every step ends with a check. Do not move on until the check passes.

## Step 1. Use Databricks Free Edition

The project needs serverless compute, Unity Catalog, declarative pipelines, SQL and Genie. Databricks Free Edition has all of them, costs nothing and does not expire. A 14-day trial on a cloud account (Azure or AWS) stops when the trial ends, so the project would stop working.

1. Sign up at https://www.databricks.com/learn/free-edition and open your workspace.
2. Note the workspace URL in the browser (it looks like `https://dbc-xxxxxxxx-xxxx.cloud.databricks.com`).

Check: you can open the workspace and see **SQL Warehouses** with a serverless starter warehouse.

## Step 2. Install the Databricks CLI and connect it

1. Install the CLI (version 0.250 or later):
   - macOS: `brew tap databricks/tap && brew install databricks`
   - Windows: `winget install Databricks.DatabricksCLI`
   - Linux: `curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh`
2. In the workspace, open your user menu, then **Settings**, **Developer**, **Access tokens**, **Generate new token**. Copy the token.
3. Run `databricks configure`. Paste the workspace URL, then the token.

Free Edition may refuse browser (OAuth) login from the CLI. A personal access token is the route that has been reported to work.

Check: `databricks current-user me` prints your user name.

## Step 3. Get the code

1. Unzip the project and open a terminal in the `order-to-delivery-databricks` folder.
2. Create an empty repository named `order-to-delivery-databricks` on GitHub (no README), then:
   ```
   git remote add origin https://github.com/t-testa/order-to-delivery-databricks.git
   git branch -M main
   git push -u origin main
   ```
3. Optional but recommended: run the local tests first (`pip install -r requirements-dev.txt` then `pytest`). They should show 51 passed.

Check: the repository is on GitHub and the CI workflow starts.

## Step 4. Validate the bundle

```
databricks bundle validate
```

Check: the output ends with `Validation OK!`.

## Step 5. Deploy

```
databricks bundle deploy
```

Check: the output ends with `Deployment complete!`. In the workspace, **Jobs & Pipelines** now shows the job `o2d-end-to-end` and the pipeline `o2d-medallion-pipeline`.

## Step 6. Run everything

```
databricks bundle run o2d_end_to_end
```

The job runs five tasks in order: `setup`, `generate_data`, `run_pipeline`, `apply_governance`, `acceptance_tests`.

Check: all five tasks are green. If one fails, send me the task name and the full error text. The most likely places for a first-run problem are:

| Task | Possible problem | What to do |
|---|---|---|
| setup | Free Edition refuses to create a new catalog | Redeploy and rerun with an existing catalog: `databricks bundle deploy --var catalog=workspace`, then `databricks bundle run o2d_end_to_end --var catalog=workspace` |
| run_pipeline | A table name or Auto Loader option is rejected | Send me the error from the pipeline event log |
| apply_governance | `ALTER MATERIALIZED VIEW` is rejected | Send me the error, the step has a fallback and I will adjust it |
| acceptance_tests | A check fails | Send me the failing rows (the task prints them) |

## Step 7. Collect the evidence (screenshots)

1. **Acceptance results.** In the SQL editor run `SELECT * FROM o2d.qa.acceptance_results ORDER BY ac_id, check_name` (replace `o2d` if you used another catalog). Screenshot 1: the result grid showing `passed = true`.
2. **Pipeline.** Open the pipeline `o2d-medallion-pipeline`. Screenshot 2: the lineage graph from bronze to gold. Screenshot 3: the data quality (expectations) view for `silver.orders`.
3. **Governance.** In Catalog Explorer open `silver.customers`. Screenshot 4: the column list showing descriptions and the `pii` tag on `email`.

Check: the four screenshots exist.

## Step 8. Genie

Follow `genie/instructions.md` to create the space, add the 10 benchmark questions and run the benchmark. Screenshot 5: the benchmark score.

Check: the score is at least 8 of 10 (acceptance criterion AC-17). If it is lower, send me the questions that failed and I will tune the instructions.

## Step 9. Send me the results

Send the five screenshots and the Genie score. I will add the real results to the README.

## If the CLI route does not work

Fallback without the CLI:

1. In the workspace create a **Git folder** from your GitHub repository.
2. Run the notebooks `src/setup/00_setup.py` and `src/data_generation/01_generate_data.py` (set the `catalog` widget).
3. Create a pipeline in the UI: serverless, default catalog `o2d`, default schema `bronze`, source files `src/pipelines/bronze.sql`, `silver.sql` and `gold.sql`, configuration key `landing_path` with value `/Volumes/o2d/bronze/landing`. Run it with a full refresh.
4. Run `src/governance/03_apply_governance.py` and `src/qa/04_run_acceptance_tests.py`.
