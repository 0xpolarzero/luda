#!/usr/bin/env python3
"""Real pinned-source HTTPS guest composition; excludes apt and host registration."""
import argparse
import contextlib
import fcntl
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(mode=0o755)  # fresh, no reuse or user-file replacement
    revision = subprocess.check_output(['git', 'rev-parse', args.revision + '^{commit}'], cwd=ROOT, text=True).strip()
    archive = output/'source.tar.gz'
    subprocess.run(['git', 'archive', '--format=tar.gz', '--prefix=luda-'+revision+'/', '-o', str(archive), revision], cwd=ROOT, check=True)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    certificate, key = output/'certificate.pem', output/'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key), '-out', str(certificate), '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    key.chmod(0o600)
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(output)))
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = 'https://127.0.0.1:%d/source.tar.gz' % server.server_port
    result = {'source_commit': revision, 'source_sha256': digest, 'scope': 'Real wrapper download/extract and extracted bootstrap; test-only callback passes skip_system=True; no apt or Mac/SSH qualification.'}
    prior_cert = os.environ.get('SSL_CERT_FILE')
    try:
        try:
            urllib.request.urlopen(url, timeout=3)
        except urllib.error.URLError as exc:
            assert isinstance(exc.reason, ssl.SSLCertVerificationError), type(exc.reason)
            result['untrusted_tls_refused'] = True
        else:
            raise AssertionError('Untrusted ephemeral certificate accepted')
        os.environ['SSL_CERT_FILE'] = str(certificate)
        tools = load(ROOT/'integrations/silo/guest/agent-tools.py', 'composition_tools')
        tools.PREFIX = output/'install'
        state = output/'state'
        state.mkdir(mode=0o700)
        release = {'schema_version': 1, 'enabled': True, 'source_url': url, 'source_sha256': digest, 'source_commit': revision}
        calls = []
        def install(source, bundle):
            calls.append(str(source))
            sys.path.insert(0, str(source/'scripts'))
            bootstrap = load(source/'scripts/bootstrap_guest.py', 'composition_bootstrap')
            with (output/'installer.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                return bootstrap.bootstrap(source, tools.PREFIX, bundle, tools.USER, skip_system=True)
        with open('/tmp/luda-live-tests.lock', 'a') as lease:
            fcntl.flock(lease, fcntl.LOCK_EX)
            first = tools.ensure(release, state, install=install)
            result['first'] = first
            assert first['state'] == 'ready', first
            selected = (tools.PREFIX/'current').resolve()
            sys.modules['manage_install'].verify_release(selected, selected.name)
            result['release_payload_integrity_verified'] = True
            manifest = selected/'release.json'
            before = (manifest.stat().st_mtime_ns, hashlib.sha256(manifest.read_bytes()).hexdigest())
            second = tools.ensure(release, state, install=install)
            assert second == first and len(calls) == 1
            assert before == (manifest.stat().st_mtime_ns, hashlib.sha256(manifest.read_bytes()).hexdigest())
            assert tools.status(release, state) == first
            subprocess.run(['runuser', '-u', tools.USER, '--', '/usr/bin/python3', '-c', 'from pathlib import Path;import sys,json;json.loads(Path(sys.argv[1]).read_text());assert Path(sys.argv[2]).read_text().startswith("---")', str(manifest), str(selected/'skills/luda/SKILL.md')], check=True, timeout=10)
            result.update(repeated_ensure_no_reinstall=True, manifest_and_skill_readable_by_desktop_user=True,
                          release_manifest_sha256=before[1], helper_sha256=hashlib.sha256((ROOT/'integrations/silo/guest/agent-tools.py').read_bytes()).hexdigest())
    finally:
        if prior_cert is None:
            os.environ.pop('SSL_CERT_FILE', None)
        else:
            os.environ['SSL_CERT_FILE'] = prior_cert
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        result['https_server_stopped'] = not thread.is_alive()
        (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
