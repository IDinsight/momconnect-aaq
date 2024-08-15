# Architecture

!!! info "This page has been customized for MomConnect."

We use docker-compose to orchestrate containers with a reverse proxy that manages all
incoming traffic to the service. The database and embedding model server are only accessed by the core
app.

<p align="center">
  <img src="../../images/architecture.png" alt="Flow"/>
</p>
