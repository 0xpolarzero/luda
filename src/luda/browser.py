"""Optional temporary owned browser provider; private bounded fixed-operation IPC."""
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid
from .common import DesktopError, checkpoint, mark_effect, process_identity
from .timing import elapsed_time

MESSAGES = {
    'STORAGE_UNAVAILABLE':'Cannot stage clipboard input; check temporary storage space and permissions.',
    'RESOURCE_UNAVAILABLE':'Cannot stage clipboard input; check process and file-descriptor resources.',
    'DEPENDENCY_MISSING':'The explicit clipboard transport requires xclip.',
    'CLIPBOARD_FAILED':'Clipboard staging could not be verified; no paste shortcut was sent at this step.',
    'CLIPBOARD_CHANGED':'Clipboard changed before paste; no shortcut was sent at this step.',
    'INPUT_HELD':'Release held input before clipboard typing.',
    'KEYBOARD_UNAVAILABLE':'Native keyboard state is unavailable.',
    'UNSUPPORTED_INPUT_STATE':'Clear latched input before clipboard typing.',

    'UNSUPPORTED_TEXT_BOUNDARY':'Browser-native input cannot split a grapheme (such as a joined emoji or combining sequence); choose complete boundaries. Offsets remain Unicode code points.',
    'TEXT_BOUNDARY_UNAVAILABLE':'Cannot verify native browser input boundaries; no input sent at this boundary.',
    'BROWSER_TIMEOUT':'Owned browser operation exceeded its deadline; inspect before retrying.',
    'STALE_TARGET':'Browser document or field changed or expired; inspect again.',
    'NOT_PROTECTED_FIELD':'Explicit secret entry requires the same observed password input; no ordinary field is accepted.',
    'PROTECTED_FIELD':'Owned browser ordinary text operations refuse protected fields.',
    'UNSUPPORTED_FIELD':'Only ordinary HTML text inputs and textareas are supported.',
    'BROWSER_SCOPE_UNSUPPORTED':'Owned text control requires one top-level page with no frames.',
    'BROWSER_CLOSED':'The temporary browser has closed; its old fields cannot be reused.',
    'COMPOSITION_UNKNOWN':'Composition provenance is unknown; no input sent.',
    'IME_COMPOSITION_ACTIVE':'Composition is active or its completion is uncertain; no automatic cancellation.',
    'FOCUS_CHANGED':'The exact browser field is not focused; inspect before acting.',
    'NOT_EDITABLE':'The field is hidden, disabled, inert or read-only.',
    'VERIFICATION_LIMIT':'Field or requested result exceeds the bounded browser verification budget.',
    'UNSUPPORTED_TEXT':'Requested text is unsupported for this HTML field; no text sent.',
    'UNSUPPORTED_SELECTION':'The field does not expose a supported text selection.',
    'SELECTION_UNVERIFIED':'The observed browser selection did not match the requested range.',
    'TEXT_CHANGED':'The browser field changed before text input; inspect before retrying.',
    'TEXT_MISMATCH':'Exact browser value did not match after input; inspect before retrying.',
    'BROWSER_ALREADY_OPEN':'This backend already owns a temporary browser.',
    'INVALID_ARGUMENT':'Invalid owned-browser argument.',
    'UNSUPPORTED_ACTION':'This browser field does not support that action.',
    'BROWSER_OPERATION_FAILED':'Owned browser operation failed; inspect current state before retrying.',
}


def capability(environment):
    executable = environment.get('LUDA_CHROMIUM_EXECUTABLE','')
    try:
        playwright_version=importlib.metadata.version('playwright') if importlib.util.find_spec('playwright') is not None else None
    except (importlib.metadata.PackageNotFoundError, ValueError, TypeError, OSError):
        playwright_version=None
    return {'available':playwright_version is not None and bool(executable) and Path(executable).is_absolute() and Path(executable).is_file() and os.access(executable,os.X_OK),
            'dependency':'optional browser extra; explicit LUDA_CHROMIUM_EXECUTABLE',
            'managed_selection_verified':bool(environment.get('LUDA_MANAGED_BROWSER_SHA256')),
            'managed_verification_scope':'launcher_startup; revalidated before each open' if environment.get('LUDA_MANAGED_BROWSER_SHA256') else None,
            'verified_executable_version':environment.get('LUDA_MANAGED_BROWSER_VERSION'),
            'launch_verified':False,
            'playwright_version':playwright_version,
            'automatic_downloads':False,'lifetime':'temporary_session',
            'unsaved_content_survives_disconnect':False,'field_limit':64000}


class OwnedBrowser:
    guard_module = 'luda._browser_guard'
    messages = MESSAGES
    supported_fields = 'ordinary HTML text inputs and textareas; inspect text_fields'

    def receipt_progress(self, value, args):
        return None

    def __init__(self, desktop):
        self.desktop=desktop
        self.process=None
        self.window_id=None
        self.pid=None
        self.start=None
        self.topology=None
        self.cleanup_proof=None

    def request(self, op, **args):
        process=self.process
        if not process or process.poll() is not None:
            raise DesktopError('BROWSER_CLOSED',self.messages['BROWSER_CLOSED'])
        mutation=op not in ('inspect','read')
        packet=(json.dumps({'op':op,**args},ensure_ascii=False,separators=(',',':'))+'\n').encode()
        if len(packet)>1024*1024:
            raise DesktopError('VERIFICATION_LIMIT',self.messages['VERIFICATION_LIMIT'])
        deadline=time.monotonic()+9
        received=b''
        selector=selectors.DefaultSelector()
        selector.register(process.stdout,selectors.EVENT_READ)
        sent=False
        try:
            while True:
                checkpoint()
                if time.monotonic()>=deadline:
                    raise DesktopError('BROWSER_TIMEOUT','Owned browser exceeded its deadline; its temporary session is being closed.',effect='uncertain' if sent and mutation else 'none')
                if packet:
                    try:
                        size=os.write(process.stdin.fileno(),packet)
                        if size:
                            sent=True;packet=packet[size:]
                    except BlockingIOError:
                        pass
                for key,_ in selector.select(.02):
                    data=os.read(key.fileobj.fileno(),65536)
                    if not data:
                        raise DesktopError('BROWSER_CLOSED','Owned browser worker stopped; its temporary session has ended.',effect='uncertain' if sent and mutation else 'none')
                    received+=data
                    if len(received)>1024*1024:
                        raise DesktopError('BROWSER_PROTOCOL_ERROR','Owned browser returned oversized data.',effect='uncertain' if sent and mutation else 'none')
                    if b'\n' in received:
                        line,extra=received.split(b'\n',1)
                        if extra:
                            raise ValueError('framing')
                        value=json.loads(line)
                        if not isinstance(value,dict):raise ValueError('shape')
                        effect=value.get('effect','uncertain' if mutation else 'none')
                        if effect not in ('none','verified','dispatched','uncertain'):raise ValueError('effect')
                        if op=='secret' and 'error' not in value and set(value)!={'effect','secret_dispatched'}:
                            raise ValueError('secret response keys')
                        raw_progress=value.pop('progress',None)
                        progress=self.receipt_progress(raw_progress,args) if op=='type' else None
                        if progress is not None:value['progress']=progress
                        if op=='secret' and 'error' not in value:
                            if set(value)!={'effect','secret_dispatched'} or effect!='dispatched' or value.get('secret_dispatched') is not True:
                                raise ValueError('secret response')
                            value={'effect':'dispatched','verification':'Protected value is never read back. Input dispatch does not verify contents; submission is separate.'}
                        mark_effect(effect)
                        if 'error' in value:
                            code=value['error']
                            details={'clipboard_may_have_changed':value.get('clipboard_may_have_changed') is True}
                            if progress is not None:details['progress']=progress
                            if value.get('provider_stage') in ('selection_sync','caret_readback'):details['provider_stage']=value['provider_stage']
                            raise DesktopError(code if code in self.messages else 'BROWSER_OPERATION_FAILED',self.messages.get(code,self.messages['BROWSER_OPERATION_FAILED']),effect=effect,details=details)
                        return value
        except DesktopError as exc:
            if exc.code not in self.messages or exc.code in ('BROWSER_CLOSED','BROWSER_TIMEOUT'):
                self.close()
                if sent and mutation:exc.effect='uncertain';mark_effect()
            raise
        except (OSError,ValueError,TypeError):
            self.close()
            if sent and mutation:mark_effect()
            raise DesktopError('BROWSER_PROTOCOL_ERROR','Owned browser communication failed; its temporary session is closed.',effect='uncertain' if sent and mutation else 'none') from None
        finally:
            selector.close()

    def open(self, url, lifetime):
        if lifetime!='temporary_session':
            raise DesktopError('INVALID_ARGUMENT','lifetime must explicitly be temporary_session.')
        if not isinstance(url,str) or len(url)>8192:
            raise DesktopError('INVALID_ARGUMENT','Use an HTTP(S) URL or about:blank.')
        try:parts=urlsplit(url)
        except ValueError:raise DesktopError('INVALID_ARGUMENT','Invalid browser URL.') from None
        if parts.username or parts.password or not (url=='about:blank' or parts.scheme in ('http','https') and parts.netloc):
            raise DesktopError('INVALID_ARGUMENT','Use HTTP(S) without embedded credentials, or about:blank.')
        if self.process and (self.process.poll() is not None or self.pid is not None and not any(w['pid']==self.pid for w in self.desktop.list_windows())):
            self.close()
        if self.process:
            raise DesktopError('BROWSER_ALREADY_OPEN',self.messages['BROWSER_ALREADY_OPEN'])
        if not capability(self.desktop.environment)['available']:
            raise DesktopError('BROWSER_ADAPTER_UNAVAILABLE','Install the optional locked browser dependencies and configure LUDA_CHROMIUM_EXECUTABLE; Luda never downloads a browser automatically.')
        from .managed_browser import verify_environment
        try:
            verify_environment(self.desktop.environment, checkpoint)
        except ValueError:
            raise DesktopError('BROWSER_SELECTION_CHANGED','Managed browser selection is unavailable or changed; review provisioning before opening it.',effect='none') from None
        self.topology=self.desktop.display().topology()
        proof_read, proof_write = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        self.cleanup_proof = proof_read
        try:
            self.process=subprocess.Popen([sys.executable,'-m',self.guard_module,str(self.desktop.runtime),str(proof_write)],
                                      stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                      env=dict(self.desktop.environment),start_new_session=True,pass_fds=(proof_write,))
        except BaseException:
            os.close(proof_read); self.cleanup_proof=None
            raise
        finally:
            os.close(proof_write)
        os.set_blocking(self.process.stdin.fileno(),False)
        os.set_blocking(self.process.stdout.fileno(),False)
        try:
            value=self.request('open',url=url,executable=self.desktop.environment['LUDA_CHROMIUM_EXECUTABLE'])
            self.pid=value['pid'];self.start=process_identity(self.pid)
            deadline=time.monotonic()+1
            while True:
                windows=[w for w in self.desktop.list_windows() if w['pid']==self.pid]
                if len(windows)==1:break
                if time.monotonic()>=deadline:
                    raise DesktopError('BROWSER_SCOPE_UNSUPPORTED','Cannot bind a unique owned browser native window.',effect='uncertain')
                time.sleep(.03)
            self.window_id=windows[0]['window_id']
            return {'window_id':self.window_id,'effect':'dispatched','browser_version':value['version'],
                    'lifetime':'temporary_session','profile':'temporary','unsaved_content_survives_disconnect':False,
                    'supported_fields':self.supported_fields,
                    'retention':'Browser and profile are deleted on backend close, reconnect or server disconnect; unsaved content is lost.'}
        except BaseException:
            self.close()
            raise

    def scoped(self, window_id, active=False):
        if window_id!=self.window_id or self.pid is None or process_identity(self.pid)!=self.start:
            raise DesktopError('STALE_TARGET',self.messages['STALE_TARGET'])
        window=self.desktop.target_window(window_id,active)
        if self.desktop.display().topology()!=self.topology:
            raise DesktopError('STALE_TARGET','Display topology changed; reopen the temporary browser provider.')
        windows=[w for w in self.desktop.list_windows() if w['pid']==self.pid]
        if len(windows)!=1 or windows[0]['window_id']!=window_id:
            raise DesktopError('BROWSER_SCOPE_UNSUPPORTED',self.messages['BROWSER_SCOPE_UNSUPPORTED'])
        return window

    def inspect(self, window_id, limit, name, role, states):
        self.scoped(window_id)
        value=self.request('inspect',limit=limit,name=name,role=role,states=states)
        for field in value['fields']:
            token=uuid.uuid4().hex
            self.desktop.elements[token]={'time':elapsed_time(),'window_id':window_id,'provider':'owned_browser','browser_token':field.pop('token')}
            field['element_id']=token
        return value

    def element(self, target, op, **kwargs):
        window=self.scoped(target['window_id'],op!='read')
        return self.request(op,token=target['browser_token'],native_target={'xid':window['xid'],'generation':window['window_id'].rsplit(':',1)[-1]},**kwargs)

    def close(self):
        process=self.process
        self.window_id=None
        if not process:return
        # SIGSTOP is recoverable: resume this exact owned guardian so EOF can
        # run its subreaper cleanup. Never kill it and abandon its descendants.
        try:
            if process.returncode is None:
                descriptor=os.pidfd_open(process.pid)
                try:signal.pidfd_send_signal(descriptor,signal.SIGCONT)
                finally:os.close(descriptor)
        except ProcessLookupError:
            pass
        try:
            process.stdin.close()
            try:process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:pass
            proof=b''
            if self.cleanup_proof is not None:
                try:proof=os.read(self.cleanup_proof,1)
                except BlockingIOError:pass
            if process.poll() is None or proof != b'1':
                raise DesktopError('BROWSER_CLEANUP_UNCONFIRMED',
                    'Temporary browser cleanup could not be confirmed; this backend will not open another browser.',effect='uncertain')
            self.process=None
            os.close(self.cleanup_proof);self.cleanup_proof=None
        finally:
            for stream in (process.stdin,process.stdout):
                try:stream.close()
                except Exception:pass
