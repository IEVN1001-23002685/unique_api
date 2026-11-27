#!/bin/sh
# Railway monta los volúmenes como root. Preparamos la propiedad para el usuario app.
# Supervisor se queda como root para poder abrir /dev/stdout y /dev/stderr (los pipes
# de logs de Railway pertenecen a root); los procesos de la API bajan a uid 10001
# desde supervisord.conf mediante gosu.
set -eu

UPLOAD_FOLDER="${UPLOAD_FOLDER:-/var/lib/unique/uploads}"

if [ "$(id -u)" = "0" ]; then
  mkdir -p /var/lib/unique "$UPLOAD_FOLDER"
  chown -R app:app /var/lib/unique "$UPLOAD_FOLDER"
  chmod 0750 /var/lib/unique "$UPLOAD_FOLDER"
fi

exec "$@"
