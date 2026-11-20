#!/usr/bin/env bash
# Despliegue de Suite Cabaña (alojateaqui.com.ar) en el VPS compartido.
#
# Corre en /opt/suite-cabana, con el repo clonado en /opt/suite-cabana/app:
#   ssh root@173.212.195.122 /opt/suite-cabana/app/deploy/deploy.sh
#
# Fuera de /opt/suite-cabana solo toca una cosa: agrega una vez el bloque del
# dominio al Caddy de entrada (el de suite-turnos), validándolo antes y volviendo
# atrás si lo rechaza. No toca contenedores, redes ni volúmenes de otras apps.
set -euo pipefail
RAIZ=/opt/suite-cabana
cd "$RAIZ"
EDGE_CADDYFILE=/opt/suite-turnos/infra/caddy/Caddyfile

# --- Código ---
# Este mismo archivo viene en el repo: se actualiza y se relanza la versión
# nueva, en vez de seguir leyendo un archivo que cambió a mitad de camino.
if [ -z "${SUITE_CABANA_ACTUALIZADO:-}" ]; then
  git -C app pull --ff-only
  SUITE_CABANA_ACTUALIZADO=1 exec bash "$RAIZ/app/deploy/deploy.sh" "$@"
fi

# --- Secretos: se generan una sola vez y no se pisan nunca ---
# CLAVE_CIFRADO cifra las credenciales de Mercado Pago de los anfitriones:
# perderla obliga a que todos las vuelvan a cargar.
umask 077
touch .env && chmod 600 .env
fijar() {
  if ! grep -q "^$1=" .env; then echo "$1=" >> .env; fi
  if grep -q "^$1=$" .env; then sed -i "s|^$1=$|$1=$2|" .env; fi
}
fijar POSTGRES_PASSWORD "$(openssl rand -hex 24)"
fijar SECRET_KEY "$(openssl rand -base64 48 | tr -d '\n=+/')"
fijar CLAVE_CIFRADO "$(openssl rand -base64 48 | tr -d '\n=+/')"
fijar DOMINIO alojateaqui.com.ar
# Dirección que anda sin DNS propio, para probar mientras el dominio no apunte.
fijar ALTERNATIVO alojateaqui.173-212-195-122.sslip.io
DOMINIO=$(sed -n 's|^DOMINIO=||p' .env)
ALTERNATIVO=$(sed -n 's|^ALTERNATIVO=||p' .env)
for d in "$DOMINIO" "$ALTERNATIVO"; do
  [[ "$d" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || { echo "ERROR: dominio no válido: $d"; exit 1; }
done
echo "Dominio: $DOMINIO (y $ALTERNATIVO)"

docker network inspect suite-turnos_edge >/dev/null \
  || { echo "ERROR: no existe la red suite-turnos_edge"; exit 1; }

# --- Contenedores ---
cp app/deploy/compose.prod.yaml compose.yaml
docker compose build --pull
docker compose up -d --wait postgres
docker compose run --rm --no-deps api alembic upgrade head
docker compose up -d --wait --remove-orphans

# Catálogo real (provincias, localidades, tipos, comodidades) y la comisión por
# defecto. Solo la primera vez: la semilla reescribe la regla de comisión y un
# redespliegue no tiene que pisar la que se haya configurado después.
if [ ! -f .catalogo-cargado ]; then
  docker compose exec -T api python -m app.semilla --solo-catalogo
  date -Iseconds > .catalogo-cargado
fi

# --- Caddy de entrada: el bloque se agrega una sola vez ---
edge_container() {
  local dir; dir=$(dirname "$EDGE_CADDYFILE")
  for c in $(docker ps -q); do
    docker inspect -f '{{range .Mounts}}{{.Source}}|{{.Destination}}{{"\n"}}{{end}}' "$c" \
      | while IFS='|' read -r src dst; do
          if [ "$src" = "$EDGE_CADDYFILE" ]; then echo "$c $dst"
          elif [ "$src" = "$dir" ]; then echo "$c $dst/Caddyfile"; fi
        done
  done
}
EDGE_MATCHES=$(edge_container | sort -u)
[ "$(printf '%s\n' "$EDGE_MATCHES" | grep -c .)" -eq 1 ] \
  || { echo "ERROR: se esperaba un solo contenedor con $EDGE_CADDYFILE:"; echo "$EDGE_MATCHES"; exit 1; }
read -r EDGE EDGE_PATH <<< "$EDGE_MATCHES"

if grep -q "^$DOMINIO, " "$EDGE_CADDYFILE"; then
  echo "El Caddy de entrada ya conoce $DOMINIO."
else
  copia="$EDGE_CADDYFILE.bak-$(date +%Y%m%d-%H%M%S)-pre-suite-cabana"
  cp -p "$EDGE_CADDYFILE" "$copia"
  # Con >> y no con sed -i: el archivo está montado en el contenedor y sed -i
  # lo reemplaza por otro, que el contenedor no vería.
  sed "s|__DOMINIO__|$DOMINIO|g; s|__ALTERNATIVO__|$ALTERNATIVO|g" \
    app/deploy/Caddyfile.edge-snippet >> "$EDGE_CADDYFILE"
  if docker exec "$EDGE" caddy validate --config "$EDGE_PATH" --adapter caddyfile >/dev/null 2>&1 \
     && docker exec "$EDGE" caddy reload --config "$EDGE_PATH" --adapter caddyfile; then
    echo "Caddy de entrada actualizado (copia previa: $copia)."
  else
    cat "$copia" > "$EDGE_CADDYFILE"
    docker exec "$EDGE" caddy reload --config "$EDGE_PATH" --adapter caddyfile || true
    echo "ERROR: el Caddy de entrada rechazó el bloque; quedó como estaba."; exit 1
  fi
fi

docker image prune -f --filter "label=com.docker.compose.project=suite-cabana" >/dev/null || true
docker compose ps --format "table {{.Name}}\t{{.Status}}"
for i in $(seq 1 30); do
  if curl -fsS "https://$ALTERNATIVO/api/v1/salud" >/dev/null 2>&1; then
    echo "Listo: https://$ALTERNATIVO"
    curl -fsS -o /dev/null "https://$DOMINIO/api/v1/salud" 2>/dev/null \
      && echo "Listo: https://$DOMINIO" \
      || echo "AVISO: https://$DOMINIO todavía no responde (¿el DNS apunta a este servidor?)."
    exit 0
  fi
  sleep 4
done
echo "AVISO: https://$ALTERNATIVO todavía no responde (el certificado puede tardar un par de minutos)."
