# Storage and resource fault qualification

Known desktop storage failures now return `STORAGE_UNAVAILABLE` with an errno
name and actionable space/quota/permissions advice. Descriptor or process
resource exhaustion returns `RESOURCE_UNAVAILABLE`. Messages omit exception
filenames, file contents and provider payloads. This covers desktop startup,
screenshot temporary storage and clipboard preparation/dispatch. Unknown
I/O errors retain their existing handling rather than being mislabeled as
a full disk; a nonzero external capture program remains a backend failure.

Clipboard staging finishes before replacing the previous owner. A failed
write therefore preserves the old clipboard and sends no paste shortcut.
The explicit temporary-file close path also removes staged bytes when a
buffered flush fails: Python 3.12's context-manager exit can otherwise defer
unlink after its close raises. Resource errors during paste conservatively
report uncertain effect, including failures after an old owner was stopped.
Startup failures after opening the display lock close that descriptor.

## Evidence types

`tests/test_storage_faults.py` has eight tests. Most inject a specific syscall
error at the runtime boundary, separately checking redaction, no snapshot,
no input, descriptor cleanup, payload-file cleanup and old-owner preservation.
One starts a separate Python process, lowers **that process's** descriptor
limit, actually exhausts descriptors, and exercises both payload-open and
subprocess-pipe allocation failure. Parent process limits are unchanged.

`tests/live_storage_filesystem.py` passed six assertions using actual kernel
ENOSPC and EROFS errors in a 64 KiB tmpfs. It creates a private user and mount
namespace with private propagation, verifies the mount namespace changed,
then fills only that bounded filesystem. After checking capture/paste failure
and cleanup, it remounts that private filesystem read-only and checks capture
and startup diagnostics. The screenshot writer is a test fixture issuing
real filesystem writes, not an actual graphical capture; no GUI dependency
is needed for this filesystem test.

```sh
.venv/bin/python -m unittest discover -s tests -p test_storage_faults.py -v
.venv/bin/python tests/live_storage_filesystem.py
```

The namespace test requires Linux `unshare` and permission to create private
user/mount namespaces. It fails explicitly if unavailable; do not substitute
a mount in the host namespace. It never fills a host filesystem. Results
and logs are written beneath `artifacts/storage`.

## Installer evidence and boundaries

`tests/test_installation_storage.py` injects owner-marker ENOSPC and metadata
fsync failure. The previous selected release and committed metadata bytes
must survive; failed preparation must leave no new release debris and a
subsequent installation must succeed. These are syscall-injection tests,
not a complete wheel installation onto the tiny filesystem.

Uninstall removes managed files individually and preserves modified or
unknown files. It is not a rollback-atomic operation: an I/O failure can
leave a partially removed release after its `current` link was removed.
A SIGKILL between creating a release directory and writing its ownership
marker also remains a narrow manual-inspection recovery case; ordinary
marker-write failures are tested, but sudden process death is different.
Quota enforcement, network/distributed filesystem errors, power-loss
ordering and every possible external screenshot-helper failure remain
outside this bounded qualification.
