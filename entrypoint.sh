#!/bin/bash
set +e

# Script trace mode
if [ "${DEBUG_MODE}" == "true" ]; then
    set -o xtrace
fi

# cd /home/app/vfzsync
cd /home/app

if [ ! -d ./config ]; then
    mkdir config
fi

if [ ! -d ./log ]; then
    mkdir log
fi

if [ ! -d ./reports ]; then
    mkdir reports
fi

DEFAULT_CONFIG=$(cat <<-END
general:
  debug: ${GENERAL_DEBUG}
  dryrun: ${GENERAL_DRYRUN}
  trace: ${GENERAL_TRACE}
  loglevel: ${GENERAL_LOGLEVEL}
  interval: ${GENERAL_INTERVAL}
  loops: ${GENERAL_LOOPS}

vpoller:
  endpoint: ${VPOLLER_ENDPOINT}
  vc_hosts: 
    - ${VPOLLER_VC_HOST_01}
    - ${VPOLLER_VC_HOST_02}
    - ${VPOLLER_VC_HOST_03}
  retries: ${VPOLLER_RETRIES}
  timeout: ${VPOLLER_TIMEOUT}

zabbix:
  url: ${ZABBIX_URL}
  username: ${ZABBIX_USERNAME}
  password: ${ZABBIX_PASSWORD}
  hostgroup: ${ZABBIX_HOSTGROUP}
  template: ${ZABBIX_TEMPLATE}
  proxy: 
    host: ${ZABBIX_PROXY_HOST}
    port: ${ZABBIX_PROXY_PORT}

command:
  url: ${COMMAND_URL}
  username: ${COMMAND_USERNAME}
  password: ${COMMAND_PASSWORD}

mail:
  server: ${MAIL_SERVER}
  port: ${MAIL_PORT}
  use_auth: ${MAIL_USE_AUTH} 
  use_ssl: ${MAIL_USE_SSL}
  use_tls: ${MAIL_USE_TLS}
  username: ${MAIL_USERNAME}
  password: ${MAIL_PASSWORD}
  sender: ${MAIL_SENDER}
  recipients: ${MAIL_RECIPIENTS}
  subject: ${MAIL_SUBJECT}

logging:
  version: 1
  formatters:
    simple:
      format: '%(asctime)s:%(module)s:%(name)s:%(levelname)s:%(message)s'
    default:
      format: '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
  handlers:
    console:
      class: logging.StreamHandler
      level: DEBUG
      formatter: simple
      stream: ext://sys.stderr
    file:
      class: logging.FileHandler
      level: ERROR
      formatter: simple
      filename: <defined_in_code.log>
    wsgi:
      class: logging.StreamHandler
      stream: ext://flask.logging.wsgi_errors_stream
      formatter: simple
  loggers:
    vfzsync:
      level: ${GENERAL_LOGLEVEL}
      handlers: [file, wsgi]
      propagate: no
    vfzlib:
      level: ${GENERAL_LOGLEVEL}
      handlers: [console, file, wsgi]
      propagate: no
    __main__:
      level: ${GENERAL_LOGLEVEL}
      handlers: [console, file]
      propagate: no
    werkzeug:
      level: WARN
      handlers: [wsgi]
      propagate: no
    gunicorn:
      level: ${GENERAL_LOGLEVEL}
      handlers: [wsgi]
      propagate: no
    gunicorn.access:
      level: WARN
      handlers: [wsgi]
      propagate: no
    gunicorn.error:
      level: ${GENERAL_LOGLEVEL}
      handlers: [wsgi]
      propagate: no
    pyzabbix:
      level: INFO
      handlers: [file, wsgi]
      propagate: no
    requests.packages.urllib3:
      level: WARN
      handlers: [file, wsgi]
      propagate: yes
  root:
    level: WARN
    handlers: [console, file, wsgi]

END
)
if [ ! -f ./config/vfzsync.yaml ]; then
    echo "$DEFAULT_CONFIG" > ./config/vfzsync.yaml
fi

MODE=$1
ENV=$2

echo Staring in ${MODE} mode, env ${ENV}

if [ ${MODE} == 'web' ]; then
  if [ ${ENV} == 'prod' ]; then
    exec $HOME/.poetry/bin/poetry run gunicorn -b :5000 --timeout 3600 --threads 1 --access-logfile - --error-logfile - vfzsync.vfz_webapp:app
  fi
  if [ ${ENV} == 'dev' ]; then
    export FLASK_APP=vfz_webapp.py
    exec $HOME/.poetry/bin/poetry run python -m flask run --host=0.0.0.0
  fi
fi

if [ ${MODE} == 'script' ]; then
  exec python -m vfzsync
fi

if [ ${MODE} == 'debug' ]; then
  while true; do sleep 60; done
fi
