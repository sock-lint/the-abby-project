# Version-specific derivative; never replace the pinned base with :latest.
FROM ghcr.io/coollabsio/coolify@sha256:3a27ba5f7f98ff7763a0a4d6715ec36e564f9622eea8f492c46f90716ea2525f

LABEL org.opencontainers.image.title="Coolify 4.1.2 bounded helper-name retry" \
      coolify.managed="true" \
      lol.bos.coolify-helper-patch.version="1" \
      lol.bos.coolify-helper-patch.base="4.1.2" \
      lol.bos.coolify-helper-patch.upstream="https://github.com/coollabsio/coolify/pull/11626"

USER root
COPY apply_patch.php helper_retry.php /opt/coolify-helper-patch/
RUN php /opt/coolify-helper-patch/apply_patch.php /var/www/html /tmp/coolify-helper-patched \
    && php -l /tmp/coolify-helper-patched/app/Jobs/ApplicationDeploymentJob.php \
    && php -l /tmp/coolify-helper-patched/bootstrap/helpers/docker.php \
    && cp /tmp/coolify-helper-patched/app/Jobs/ApplicationDeploymentJob.php /var/www/html/app/Jobs/ApplicationDeploymentJob.php \
    && cp /tmp/coolify-helper-patched/bootstrap/helpers/docker.php /var/www/html/bootstrap/helpers/docker.php \
    && cp /tmp/coolify-helper-patched/patch-receipt.json /opt/coolify-helper-patch/patch-receipt.json \
    && chown www-data:www-data /var/www/html/app/Jobs/ApplicationDeploymentJob.php /var/www/html/bootstrap/helpers/docker.php \
    && rm -rf /tmp/coolify-helper-patched
# Gate HTTP/PHP ingress until app:init has completed its startup cleanup.
# Keep flat dependency files: dependencies.d would supersede nginx's old edge.
# Graph: nginx -> php-fpm + init-script -> init-seeder -> db-migration.
# app:init runs CLI PHP and external requests; it does not use local HTTP/FPM.
RUN printf '%s\n' \
      '419df54ad7888a246b35fd79beb92b28595e761692f45ee99e228d4be33712dd  /etc/s6-overlay/s6-rc.d/nginx/dependencies' \
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  /etc/s6-overlay/s6-rc.d/php-fpm/dependencies' \
      '014498f24a848b7d13e9add67074640ea89094c1d59d2750690313db16f9f881  /var/www/html/app/Console/Commands/Init.php' \
      | sha256sum -c - \
    && test ! -e /etc/s6-overlay/s6-rc.d/nginx/dependencies.d \
    && test ! -e /etc/s6-overlay/s6-rc.d/php-fpm/dependencies.d \
    && printf '\ninit-script\n' >> /etc/s6-overlay/s6-rc.d/nginx/dependencies \
    && printf 'init-script\n' >> /etc/s6-overlay/s6-rc.d/php-fpm/dependencies
USER www-data
