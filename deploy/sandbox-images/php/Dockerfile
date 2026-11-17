# The sandbox image of the PHP packs (LR.30, `app.stacks.packs._sandbox`): PHP and Composer beside Node and the
# browsers, for container mode, where every agent command runs in a container of its own - the service's suite runs
# under Playwright and starts the PHP service from inside the same container.
# Built by `scripts/loop/build_sandbox_images.sh`. PHP matches the packs' `PHP_VERSION` (8.4), which Ubuntu 24.04
# does not ship, so it comes from the PHP packaging PPA; the extensions are the worker image's set.
ARG PLAYWRIGHT_VERSION=1.64.0
ARG COMPOSER_VERSION=2.8
FROM composer:${COMPOSER_VERSION} AS composer

FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble

ARG PHP_VERSION=8.4

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git unzip software-properties-common \
    && add-apt-repository -y ppa:ondrej/php \
    && apt-get update && apt-get install -y --no-install-recommends \
        "php${PHP_VERSION}-cli" "php${PHP_VERSION}-xml" "php${PHP_VERSION}-mbstring" \
        "php${PHP_VERSION}-curl" "php${PHP_VERSION}-sqlite3" \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --set php "/usr/bin/php${PHP_VERSION}"

COPY --from=composer /usr/bin/composer /usr/local/bin/composer

RUN php --version && composer --version && node --version
