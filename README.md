# Databricks CI/CD Pipeline

This project automates production deployment of an Azure Databricks Python bundle using GitHub Actions. Developers edit and test code in a Databricks development Git folder, push a working branch to GitHub, and merge a pull request into `main`. GitHub then validates the bundle, synchronizes its source files into `/Workspace/Shared/live`, builds a Python wheel, and creates or updates the production jobs and pipelines.

The project includes an order transformation notebook job and an ETL pipeline defined as bundle resources.

## Technology

- **Azure Databricks:** notebooks, Lakeflow Jobs, and pipelines.
- **GitHub:** source control and pull requests.
- **GitHub Actions:** automated validation and deployment.
- **Declarative Automation Bundles:** deployment configuration and resource definitions.
- **Python 3.12, uv, and Hatchling:** Python package build.
- **Unity Catalog:** catalog, schema, and data permissions.
- **Serverless compute:** execution of the order transformation notebook job.

## Repository structure

The deployment uses these paths. Other package and resource files may also be present.

```text
.github/workflows/deploy-prod.yml
CICDPipeline/databricks.yml
CICDPipeline/pyproject.toml
CICDPipeline/resources/order_data_transformation_job.job.yml
CICDPipeline/src/Order_Data_Transformation.ipynb
```

The Databricks Git folders named `dev` and `prod` are separate checkouts of the repository. They are not directories that the GitHub workflow navigates into. The bundle root in GitHub is `CICDPipeline`.

## Deployment flow

1. A developer pulls the latest `main` into the development Git folder.
2. The developer creates a working branch, edits code, and tests it in dev.
3. The developer commits and pushes the branch, then opens a PR into `main`.
4. Merging the PR triggers GitHub Actions.
5. The runner checks out the repository, prepares Python 3.12, and installs the Databricks CLI and uv.
6. The CLI authenticates with a Databricks service principal.
7. The workflow validates the `prod` bundle target and synchronizes its files into `live`.
8. Bundle deployment builds and uploads the wheel and creates or updates the configured resources.

**Current trigger:** pushes to `main` and manual `workflow_dispatch` runs. Opening a PR or pushing a feature branch does not trigger this workflow.

**Current checks:** bundle configuration validation after merge. Automated Python tests, PR validation, staging promotion, and production approval are not yet configured in this workflow.

## Environments and destinations

| Setting | Development | Production |
| --- | --- | --- |
| Bundle target | `dev` | `prod` |
| Deployment mode | `development` | `production` |
| Catalog | `databrucks-ci-cd-pipelines` | `databrucks-ci-cd-pipelines` |
| Schema | `${workspace.current_user.short_name}` | `prod` |
| Source file destination | Bundle defaults | `/Workspace/Shared/live` |

Both targets currently use the same Databricks workspace and catalog. Their schemas separate development and production outputs. Notebook and pipeline code must use the configured parameters rather than hard-coded development locations.

The production `root_path` stores bundle deployment state. Keep the configured path stable across deployments. The `file_path` setting controls the source file destination:

```yaml
file_path: /Workspace/Shared/live
```

Synchronization follows bundle include/exclude rules. The `live` folder contains synchronized project files, not a complete Git clone with history. The separate Databricks `prod` Git checkout is not automatically pulled by this workflow.

## Authentication

GitHub authenticates using a Databricks-managed service principal named `github-prod-deployer` and OAuth machine-to-machine authentication.

Create these repository secrets under **Settings > Secrets and variables > Actions**:

| Secret | Purpose |
| --- | --- |
| `DATABRICKS_HOST` | Production workspace URL |
| `DATABRICKS_CLIENT_ID` | Service principal application/client ID |
| `DATABRICKS_CLIENT_SECRET` | Databricks OAuth secret |

The workflow uses `DATABRICKS_AUTH_TYPE: oauth-m2m`. Its working authentication setup uses an OAuth secret with `all-apis`, matching the CLI's token request. Resource permissions still restrict the principal's access; this scope does not make it an administrator.

Never commit credentials. Rotate secrets before expiry, revoke exposed secrets, and update the GitHub secret when rotating. Workload identity federation is a future improvement that would remove the stored client secret.

## Required permissions

Grant the deployment principal the following access:

| Resource | Permissions |
| --- | --- |
| `/Workspace/Shared/live` | `CAN MANAGE` |
| Configured production bundle deployment-state folder | `CAN MANAGE` |
| Catalog `databrucks-ci-cd-pipelines` | `USE CATALOG` |
| Schema `databrucks-ci-cd-pipelines.prod` | `USE SCHEMA`, `CREATE TABLE`, `CREATE MATERIALIZED VIEW` |

Additional permissions may be required for source tables, volumes, compute, or other resources referenced by the workloads. Workspace folder permissions and Unity Catalog privileges are separate.

## Deployment commands

Run commands from the bundle directory:

```bash
cd CICDPipeline
databricks current-user me
databricks bundle validate -t prod
databricks bundle sync -t prod --full
databricks bundle deploy -t prod
```

The workflow sets `defaults.run.working-directory: CICDPipeline` so these commands find `databricks.yml`.

The bundle builds its wheel with:

```yaml
artifacts:
  python_artifact:
    type: whl
    build: uv build --wheel
```

`pyproject.toml` requires Python `>=3.12,<3.13` and uses Hatchling as the build backend. Bundle deployment also synchronizes files; the explicit sync step makes the upload to `live` visible in the workflow.

## Serverless notebook dependencies

The order transformation job uses a job environment to install the built wheel. Task-level `libraries` is not supported for this serverless task.

The following excerpt belongs under the job definition in its resource YAML:

```yaml
tasks:
  - task_key: order_data_transformation
    notebook_task:
      notebook_path: ../src/Order_Data_Transformation.ipynb
    environment_key: default

environments:
  - environment_key: default
    spec:
      environment_version: "2"
      dependencies:
        - ../dist/*.whl
```

Paths in this resource file are relative to its location under `resources`. The task also receives the job's `catalog` and `schema` parameters. Notebook code must read and use them.

## Deploying versus running

Deployment creates or updates resource definitions. The workflow does not explicitly execute the job after deployment. A job runs when its trigger fires or someone selects **Run now**.

To execute the order transformation job through the CLI:

```bash
databricks bundle run -t prod order_data_transformation_job
```

The job's periodic trigger is configured with an interval of one day; it is not a fixed daily wall-clock schedule. Job execution uses compute and can incur charges.

## Updating an existing production job

With the same deployment state, target, and resource key, the bundle normally updates the existing tracked job instead of creating another job on each release. A matching display name alone does not link a manually created job to the bundle.

Keep the bundle name, production deployment path, and resource keys stable. Renaming keys, changing deployment state locations, or removing resources can affect what is created, updated, or deleted.

Deploy when affected production work is idle. Synchronizing into the shared `live` folder can change files that a running workload may read. GitHub workflow concurrency limits overlapping deployments; it does not wait for Databricks job runs.

## Troubleshooting

| Error | Resolution |
| --- | --- |
| `Scopes 'all-apis' are not assigned` | Generate a compatible OAuth secret, update the GitHub secret, and revoke the old secret. |
| `databricks.yml not found` | Set the workflow working directory to `CICDPipeline`. |
| `yaml: did not find expected key` | Fix YAML indentation and nesting; use spaces rather than tabs. |
| `Libraries field is not supported for serverless task` | Put wheel dependencies in the job environment and reference it with `environment_key`. |
| `does not have USE CATALOG` | Grant catalog access and the required production schema privileges. |
| `dependency failed` | Find and fix the first resource creation error before the follow-on failures. |
| Deployment identity permission recommendation | Explicitly include the deploying service principal's client ID in the bundle permissions if required. This does not replace catalog or folder grants. |

For a failed run, open **GitHub > Actions > run > deploy**, expand the first failed step, and inspect its actual error. `Exit code 1` alone does not identify the cause.

After changing only secrets or external permissions, rerun the failed job. After fixing source or workflow files, merge the new commit and inspect its new run; rerunning an older run uses the older commit.

## Future improvements

- Validate and test pull requests before merge.
- Add unit tests and integration tests for transformations.
- Add staging deployment and production approval.
- Replace stored OAuth secrets with workload identity federation.
- Pin and maintain action and CLI versions.
- Add release isolation and an active-run check before any write to production files.

## Documentation

- [Bundle configuration](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/settings)
- [OAuth service principal authentication](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/auth/oauth-m2m)
- [GitHub workload identity federation](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/auth/provider-github)
- [Bundle serverless examples](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/examples)
- [Unity Catalog with pipelines](https://learn.microsoft.com/en-us/azure/databricks/ldp/unity-catalog)
