# Quick Setup with Docker Compose

!!! info "This page has been customized for MomConnect."

## Quick setup

!!! warning "You need to have installed [Docker](https://docs.docker.com/get-docker/)"

**Step 1:** Clone the [AAQ repository](https://github.com/IDinsight/ask-a-question).

```shell
git clone git@github.com:IDinsight/momconnect-aaq.git
```

**Step 2:** Navigate to the `deployment/docker-compose/` subfolder.

```shell
cd deployment/docker-compose/
```

**Step 3:** Copy `template.*.env` files to `.*.env`:

```shell
cp template.base.env .base.env
cp template.core_backend.env .core_backend.env
```

**Step 4:** <s>Configure LiteLLM Proxy server</s> (Not applicable for MomConnect)

**Step 5:** Run docker-compose

```shell
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
   --profile huggingface-embeddings -p mc-aaq-stack up -d --build
```

You can now view the AAQ admin app at `https://$DOMAIN/` (by default, this should be [https://localhost/](https://localhost/)) and the API documentation at
`https://$DOMAIN/api/docs` (you can also test the endpoints here).

**Step 6:** Shutdown containers

```shell
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
   --profile huggingface-embeddings -p mc-aaq-stack down
```

## Ready to deploy?

See [Configuring AAQ](./config-options.md) to configure your app.
