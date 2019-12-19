#!/bin/sh

set -e

if [ "$1" = "setup" ]
then
  set -x
  apt-get -q update
  DEPS=$(./share/requires.py -p lava-server -d debian -s stretch -n)
  apt-get install --no-install-recommends --yes $DEPS
  DEPS=$(./share/requires.py -p lava-server -d debian -s stretch-backports -n)
  apt-get install --no-install-recommends --yes -t stretch-backports $DEPS
  DEPS=$(./share/requires.py -p lava-server -d debian -s stretch -n -u)
  apt-get install --no-install-recommends --yes $DEPS
  DEPS=$(./share/requires.py -p lava-server -d debian -s stretch-backports -n -u)
  apt-get install --no-install-recommends --yes -t stretch-backports $DEPS
else
  set -x
  PYTHONPATH=. pytest-3 --cache-clear -v --junitxml=common.xml tests/lava_common
  PYTHONPATH=. pytest-3 --cache-clear --ds lava_server.settings.development -v --junitxml=server.xml tests/lava_scheduler_app tests/lava_results_app tests/linaro_django_xmlrpc tests/lava_rest_app tests/lava_server
fi
