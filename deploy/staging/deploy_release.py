#!/usr/bin/env python3
"""Update an already-migrated V2 staging site; never restore or migrate data."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path('/root/Custom-Events-Staging-V2')
PROJECT = 'platform-v2-staging'


def run(args, *, env=None, capture=False):
    return subprocess.run(args, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def atomic_write(path, content):
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as target:
            target.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Deployment:
    def __init__(self, root, revision, runner=run, sleeper=time.sleep):
        if not re.fullmatch('[0-9a-f]{40}', revision):
            raise ValueError('A full lowercase Git revision is required.')
        self.root, self.revision, self.run = Path(root), revision, runner
        self.sleep = sleeper
        self.release = self.root / 'releases' / revision
        self.env_file = self.root / '.env.v2.staging'
        for path in (self.root, self.release, self.env_file):
            if not path.exists() or path.is_symlink() or path.resolve() != path:
                raise ValueError('Expected a prepared V2 release and independent server configuration.')

    def inspect(self, name):
        return json.loads(self.run(['docker', 'inspect', name], capture=True))[0]

    def compose(self, revision, *args):
        environment = os.environ.copy()
        environment['STAGING_IMAGE_TAG'] = revision
        return self.run(['docker', 'compose', '--env-file', str(self.env_file), '-f',
            str(self.root / 'releases' / revision / 'compose.v2.staging.yml'), '-p', PROJECT,
            *args], env=environment)

    def command(self, revision, *args):
        return self.compose(revision, 'run', '--rm', '--no-deps', '-T', '--interactive=false',
                            'migrate', 'python', 'manage.py', *args)

    def activate(self, revision):
        self.command(revision, 'collectstatic', '--noinput')
        self.compose(revision, 'up', '-d', '--no-build', '--wait', '--wait-timeout', '180',
                     'backend', 'frontend')
        # nginx resolves upstream container addresses at startup: recreate it only
        # after the replacement backend/frontend have passed their health checks.
        self.compose(revision, 'up', '-d', '--no-build', '--no-deps', '--force-recreate', 'gateway')
        for url in ('http://127.0.0.1/api/v2/site/', 'http://127.0.0.1/'):
            for attempt in range(5):
                try:
                    self.compose(revision, 'exec', '-T', '--interactive=false', 'gateway',
                                 'wget', '-q', '--timeout=20', '-O', '/dev/null', url)
                    break
                except subprocess.CalledProcessError:
                    if attempt == 4:
                        raise
                    self.sleep(2)

    def execute(self):
        database = self.inspect(PROJECT + '-db-1')
        labels = database['Config']['Labels']
        if (labels.get('com.docker.compose.project') != PROJECT
                or labels.get('com.docker.compose.service') != 'db'
                or not database['State']['Running']
                or not any(m.get('Name') == PROJECT + '_staging_postgres'
                           and m['Destination'].rstrip('/') == '/var/lib/postgresql/data'
                           for m in database['Mounts'])):
            raise ValueError('The isolated V2 staging database must already be running.')
        services = self.run(['docker', 'ps', '--filter', 'label=com.docker.compose.project=' + PROJECT,
                            '--format', '{{.Label "com.docker.compose.service"}}'], capture=True)
        if any(service.startswith('jobs-') for service in services.splitlines()):
            raise ValueError('Active V2 workers require a reviewed worker deployment procedure.')
        backend = self.inspect(PROJECT + '-backend-1')
        previous_config = Path(backend['Config']['Labels']['com.docker.compose.project.config_files'])
        previous = previous_config.parent.name
        if (not re.fullmatch('[0-9a-f]{40}', previous)
                or previous_config != self.root / 'releases' / previous / 'compose.v2.staging.yml'
                or backend['Config']['Image'] != f'{PROJECT}-backend:{previous}'):
            raise ValueError('Cannot identify the existing immutable V2 release for rollback.')
        # Require the previous images before touching any service. Never pull a
        # replacement for an unknown rollback image or switch Compose projects.
        for revision in dict.fromkeys((previous, self.revision)):
            self.run(['docker', 'image', 'inspect', f'{PROJECT}-backend:{revision}',
                      f'{PROJECT}-frontend:{revision}'], capture=True)
        self.compose(self.revision, 'config', '--quiet')
        self.command(self.revision, 'check')
        try:
            self.command(self.revision, 'migrate', '--check')
        except subprocess.CalledProcessError:
            raise RuntimeError('Pending database migrations: review and apply them on isolated staging before retrying CI. The running website was not replaced.') from None
        # There are deliberately NO migrate/restore/down/prune operations here.
        # This guarantees rollback does not run old code against an unreviewed schema.
        try:
            self.activate(self.revision)
        except subprocess.CalledProcessError:
            print('Activation failed; restoring the previous V2 application images.', flush=True)
            self.activate(previous)
            raise RuntimeError('Deployment failed; previous V2 release restored.') from None
        lines = self.env_file.read_text().splitlines()
        lines = [line for line in lines if not line.startswith('STAGING_IMAGE_TAG=')]
        atomic_write(self.env_file, '\n'.join([*lines, 'STAGING_IMAGE_TAG=' + self.revision]) + '\n')
        atomic_write(self.root / 'current-release', self.revision + '\n')
        atomic_write(self.root / 'last-deployment.json', json.dumps({
            'revision': self.revision, 'previous_revision': previous, 'status': 'healthy',
            'database_migrated': False, 'workers_started': False,
        }, indent=2) + '\n')
        print(f'V2 staging is healthy at revision {self.revision}.', flush=True)


def main():
    import fcntl  # The deployment entry point runs on the Linux VPS.
    os.umask(0o077)
    if len(sys.argv) != 2:
        raise ValueError('Usage: deploy_release.py FULL_COMMIT_SHA')
    if ROOT.is_symlink() or ROOT.resolve() != ROOT:
        raise ValueError('Invalid V2 staging root.')
    lock = ROOT / '.prepare.lock'
    if lock.is_symlink():
        raise ValueError('Invalid deployment lock.')
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        Deployment(ROOT, sys.argv[1]).execute()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
