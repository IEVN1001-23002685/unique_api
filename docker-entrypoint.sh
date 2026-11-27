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

# Las imágenes reales publicadas viajan en la imagen. Se copian solo si faltan,
# para que un redeploy no dependa de que Railway conserve un volumen efímero y
# para no sobrescribir archivos subidos después desde el panel de administración.
if [ -d /app/seed_uploads ]; then
  for archivo in /app/seed_uploads/*; do
    [ -f "$archivo" ] || continue
    nombre=$(basename "$archivo")
    if [ ! -f "$UPLOAD_FOLDER/$nombre" ]; then
      cp "$archivo" "$UPLOAD_FOLDER/$nombre" 2>/dev/null || true
    fi
  done
  chown -R app:app "$UPLOAD_FOLDER" 2>/dev/null || true
fi

exec "$@"
