# Technology Stack

## Selected Technology Stack
- **Language:** Java
- **Framework:** Spring Boot
- **Frontend framework:** not stated
- **Database:** SQLite
- **Testing framework:** JUnit 5 with Spring Boot Test for unit tests, Playwright (request fixture) for acceptance tests
- **Additional tools:** Spring Boot Actuator
- **Kind of product:** http api

## Rationale
The product intake explicitly requires Java with Spring Boot, which maps directly to the available stack: HTTP service in Java on Spring Boot. This is an HTTP API (other programs call it over HTTP), so product_kind is http_api and frontend_framework is empty.

SQLite is chosen over JSON file persistence for ACID transaction safety and reliable concurrent write handling while still being a single file under DATA_DIR with no separate server process — both options satisfy the intake's open choice, but SQLite better protects against data corruption on crash or concurrent writes.

Spring Boot Actuator provides the required GET /health endpoint out of the box with negligible overhead.

Testing uses JUnit 5 with Spring Boot Test for unit tests (the language's standard testing stack, covering business logic and controller layer) and Playwright request fixture for acceptance tests against the running HTTP service. Both are listed in the available stacks and cover different verification concerns — neither can replace the other.

<!-- Generated from this stage's structured response. Editing this file does not change what the pipeline reads. -->
