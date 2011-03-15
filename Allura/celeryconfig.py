import sys
import pkg_resources

print sys.argv

BROKER_HOST = "localhost"
BROKER_PORT = 5672
BROKER_USER = "testuser"
BROKER_PASSWORD = "testpw"
BROKER_VHOST = "testvhost"
CELERY_RESULT_BACKEND = "amqp"
ALLURA_CONFIG='config:/home/rick446/src/forge/Allura/development.ini#task'
CELERY_IMPORTS = ['allura']

visited = set()
for ep in pkg_resources.iter_entry_points('allura'):
    visited.add(ep.module_name)
CELERY_IMPORTS += list(sorted(visited))
print sorted(CELERY_IMPORTS)
