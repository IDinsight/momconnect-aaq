# Configuring AAQ

!!! info "This page has been customized for MomConnect."

All required and optional environment variables are defined in
`deployment/docker-compose/template.*.env` files.

You will need to copy the
templates into `.*.env` files.

```shell
cp template.base.env .base.env
cp template.core_backend.env .core_backend.env
```

See the rest of
this page for more information on the environment variables.

<a name="template-env-guide"></a>
!!! note "Understanding the template environment files `template.*.env`"

    For production, make sure you confirm or update the ones marked "change for production" at the least.

    1. Secrets have been marked with 🔒.
    2. All optional values have been commented out. Uncomment to customize for your own case.

## AAQ-wide configurations

The base environment variables are shared by `caddy` (reverse proxy), `core_backend`,
and `admin_app` during run time.

If not done already, copy the template environment file to `.base.env`

```shell
cd deployment/docker-compose/
cp template.base.env .base.env
```

Then, edit the environment variables according to your need ([guide](#template-env-guide) on updating the template):

```shell title="<code>deployment/docker-compose/template.base.env</code>"
--8<-- "deployment/docker-compose/template.base.env"
```

## Configuring the backend (`core_backend`)

### Environment variables for the backend

If not done already, copy the template environment file to `.core_backend.env` ([guide](#template-env-guide) on updating the template):

```shell
cd deployment/docker-compose/
cp template.core_backend.env .core_backend.env
```

The `core_backend` uses the following required and optional (commented out) environment variables.

```shell title="<code>deployment/docker-compose/template.core_backend.env</code>"
--8<-- "deployment/docker-compose/template.core_backend.env"
```

### Other configurations for the backend

You can view all configurations that `core_backend` uses in
`core_backend/app/*/config.py`
files -- for example, [`core_backend/app/config.py`](https://github.com/IDinsight/ask-a-question/blob/main/core_backend/app/config.py).

??? Note "Environment variables take precedence over the config file."
    You'll see in the config files that we get parameters from the environment and if
    not found, we fall back on defaults provided. So any environment variables set
    will override any defaults you have set in the config file.

## Configuring optional components

See instructions for setting these in the documentation for the specific optional
component at [Optional components](../components/index.md#internal-components).
