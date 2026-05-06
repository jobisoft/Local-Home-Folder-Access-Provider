#!/usr/bin/env python3
"""
Native messaging host for the vfs-toolkit file system provider.

Relays VFS commands from the Thunderbird extension to the real local file system.
VFS paths (e.g. "/documents/foo.txt") are resolved relative to ROOT, which
defaults to the user's home directory.

Message framing (Mozilla native messaging protocol):
  - Each message is preceded by a 4-byte unsigned int (native byte order)
    that gives the byte length of the following UTF-8 JSON payload.

Command dispatch:
  Incoming: { "requestId": str, "cmd": str, ...args }
  Outgoing: { "requestId": str, "ok": true,  "result": any,  "partial": bool }
           | { "requestId": str, "ok": false, "error": str, "errorCode": str|null }

File content is transported as base64 to survive JSON encoding. Files larger
than CHUNK_SIZE bytes are split across multiple messages, each carrying
"partial": true except for the final one.

Write uploads larger than CHUNK_SIZE arrive as multiple writeFile messages
sharing the same "uploadId". Intermediate messages carry "more": true; the
last (or only) one carries "more": false (or omits the field).
"""

import sys
import json
import struct
import os
import shutil
import mimetypes
import base64
import stat

# ── Configuration ──────────────────────────────────────────────────────────────

ROOT = os.path.expanduser('~')  # VFS "/" maps to the user's home directory

# Legacy Windows compat junctions ("My Documents", "Meine Dokumente", etc.) set
# all three flags AND have a deny-list ACL that blocks enumeration.
WIN_LEGACY_JUNCTION_MASK = (
    stat.FILE_ATTRIBUTE_HIDDEN
    | stat.FILE_ATTRIBUTE_SYSTEM
    | stat.FILE_ATTRIBUTE_REPARSE_POINT
)

# Maximum bytes of raw file data per message.  At 4/3 base64 expansion this
# keeps every JSON message safely under Mozilla's 1 MB native-messaging limit.
CHUNK_SIZE = 700 * 1024  # 700 KB binary → ~933 KB base64

# ── Native messaging framing ───────────────────────────────────────────────────

def get_message():
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) == 0:
        sys.exit(0)
    message_length = struct.unpack('@I', raw_length)[0]
    message = sys.stdin.buffer.read(message_length).decode('utf-8')
    return json.loads(message)


def send_message(content):
    encoded = json.dumps(content, separators=(',', ':')).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('@I', len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()

# ── Path helpers ───────────────────────────────────────────────────────────────

def _is_legacy_junction(st):
    """True for the deny-listed Windows compat junctions ('My Documents', etc.)."""
    attrs = getattr(st, 'st_file_attributes', None)
    return attrs is not None and (attrs & WIN_LEGACY_JUNCTION_MASK) == WIN_LEGACY_JUNCTION_MASK


def _is_reparse_point(st):
    """True for any symlink/junction (reparse point on Windows, S_ISLNK on POSIX)."""
    attrs = getattr(st, 'st_file_attributes', None)
    if attrs is not None:
        return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return stat.S_ISLNK(st.st_mode)


def real_path(vfs_path, follow_symlinks=False):
    """Resolve a VFS path to an absolute real path under ROOT.

    Textually rejects '..'-style escapes via os.path.normpath. Then walks each
    path component under ROOT and rejects:
      * legacy Windows compat junctions — always.
      * any other reparse point (symlink / junction) — when follow_symlinks is False.
    Components past the first FileNotFoundError are not checked, so creating a
    new file/folder at a not-yet-existing leaf still works.
    """
    rel = vfs_path.lstrip('/')
    target = os.path.normpath(os.path.join(ROOT, rel)) if rel else ROOT
    if not (target == ROOT or target.startswith(ROOT + os.sep)):
        raise PermissionError(f'Path escapes root: {vfs_path}')

    if target != ROOT:
        current = ROOT
        for comp in os.path.relpath(target, ROOT).split(os.sep):
            current = os.path.join(current, comp)
            try:
                st = os.lstat(current)
            except FileNotFoundError:
                break  # not-yet-existing leaf — parents already validated
            if _is_legacy_junction(st):
                raise PermissionError(f'Legacy Windows junction not accessible: {vfs_path}')
            if _is_reparse_point(st) and not follow_symlinks:
                raise PermissionError(f'symlink support not enabled: {vfs_path}')

    return target


def guess_mime(path):
    mime, _ = mimetypes.guess_type(path)
    return mime or 'application/octet-stream'

# ── Command handlers ───────────────────────────────────────────────────────────

def cmd_list(args):
    path = args.get('path', '/')
    show_hidden = args.get('showHidden', False)
    follow_symlinks = args.get('followSymlinks', False)
    real = real_path(path, follow_symlinks)
    if not os.path.isdir(real):
        raise FileNotFoundError(f'Not a directory: {path}')

    entries = []
    for name in os.listdir(real):
        full = os.path.join(real, name)
        prefix = path.rstrip('/')
        entry_path = f'{prefix}/{name}'
        try:
            st = os.stat(full, follow_symlinks=False)
        except OSError:
            continue

        if _is_legacy_junction(st):
            continue

        attrs = getattr(st, 'st_file_attributes', None)  # None on non-Windows
        if attrs is not None:
            is_hidden = bool(attrs & stat.FILE_ATTRIBUTE_HIDDEN)   # Windows
        else:
            is_hidden = name.startswith('.')                       # Linux/macOS
        if is_hidden and not show_hidden:
            continue

        if os.path.isdir(full):
            entries.append({'name': name, 'path': entry_path, 'kind': 'directory'})
        else:
            entries.append({
                'name': name,
                'path': entry_path,
                'kind': 'file',
                'size': st.st_size,
                'lastModified': int(st.st_mtime * 1000),
            })

    entries.sort(key=lambda e: (0 if e['kind'] == 'directory' else 1, e['name'].lower()))
    return entries, False  # (result, is_chunked)


def cmd_read_file(request_id, args):
    """Read a file; returns an iterator of (partial, result_dict) pairs."""
    path = args['path']
    follow_symlinks = args.get('followSymlinks', False)
    real = real_path(path, follow_symlinks)
    if not os.path.isfile(real):
        raise FileNotFoundError(f'File not found: {path}')
    st = os.stat(real)
    name = os.path.basename(real)
    mime = guess_mime(real)
    last_modified = int(st.st_mtime * 1000)

    with open(real, 'rb') as f:
        first = True
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                # Empty file: send a single empty response
                if first:
                    send_message({
                        'requestId': request_id, 'ok': True, 'partial': False,
                        'result': {'name': name, 'type': mime, 'lastModified': last_modified,
                                   'content': ''},
                    })
                return
            next_chunk = f.read(1)  # peek: is there more?
            has_more = bool(next_chunk)
            if next_chunk:
                f.seek(f.tell() - 1)  # un-peek

            result = {'content': base64.b64encode(chunk).decode('ascii')}
            if first:
                result['name'] = name
                result['type'] = mime
                result['lastModified'] = last_modified
                first = False

            send_message({
                'requestId': request_id,
                'ok': True,
                'partial': has_more,
                'result': result,
            })


# In-flight chunked upload buffers: uploadId → { path, overwrite, data }
_write_buffers = {}


def cmd_write_file(args):
    path = args['path']
    overwrite = args.get('overwrite', False)
    upload_id = args.get('uploadId')
    more = args.get('more', False)
    follow_symlinks = args.get('followSymlinks', False)
    content = base64.b64decode(args.get('content', ''))

    if upload_id is None:
        # Single-chunk write (file fits in one message)
        real = real_path(path, follow_symlinks)
        if not overwrite and os.path.exists(real):
            raise FileExistsError(f'File already exists: {path}')
        os.makedirs(os.path.dirname(real) or ROOT, exist_ok=True)
        with open(real, 'wb') as f:
            f.write(content)
        return None, False

    # Multi-chunk write
    if upload_id not in _write_buffers:
        # First chunk: validate before allocating the buffer
        real = real_path(path, follow_symlinks)
        if not overwrite and os.path.exists(real):
            raise FileExistsError(f'File already exists: {path}')
        _write_buffers[upload_id] = {
            'path': path, 'overwrite': overwrite,
            'followSymlinks': follow_symlinks, 'data': bytearray(),
        }

    _write_buffers[upload_id]['data'].extend(content)

    if more:
        return None, False  # ack intermediate chunk, keep buffering

    # Last chunk — flush to disk
    buf = _write_buffers.pop(upload_id)
    real = real_path(buf['path'], buf['followSymlinks'])
    os.makedirs(os.path.dirname(real) or ROOT, exist_ok=True)
    with open(real, 'wb') as f:
        f.write(bytes(buf['data']))
    return None, False


def cmd_add_folder(args):
    path = args['path']
    follow_symlinks = args.get('followSymlinks', False)
    real = real_path(path, follow_symlinks)
    if os.path.exists(real):
        raise FileExistsError(f'Folder already exists: {path}')
    os.makedirs(real)
    return None, False


def cmd_move_file(args):
    follow_symlinks = args.get('followSymlinks', False)
    old_real = real_path(args['oldPath'], follow_symlinks)
    new_real = real_path(args['newPath'], follow_symlinks)
    overwrite = args.get('overwrite', False)
    if not overwrite and os.path.exists(new_real):
        raise FileExistsError(f'Target already exists: {args["newPath"]}')
    os.makedirs(os.path.dirname(new_real) or ROOT, exist_ok=True)
    shutil.move(old_real, new_real)
    return None, False


def cmd_move_folder(args):
    follow_symlinks = args.get('followSymlinks', False)
    old_real = real_path(args['oldPath'], follow_symlinks)
    new_real = real_path(args['newPath'], follow_symlinks)
    merge = args.get('merge', False)
    if not merge and os.path.exists(new_real):
        raise FileExistsError(f'Target already exists: {args["newPath"]}')
    if merge and os.path.exists(new_real):
        for item in os.listdir(old_real):
            shutil.move(os.path.join(old_real, item), os.path.join(new_real, item))
        os.rmdir(old_real)
    else:
        shutil.move(old_real, new_real)
    return None, False


def cmd_copy_file(args):
    follow_symlinks = args.get('followSymlinks', False)
    old_real = real_path(args['oldPath'], follow_symlinks)
    new_real = real_path(args['newPath'], follow_symlinks)
    overwrite = args.get('overwrite', False)
    if not overwrite and os.path.exists(new_real):
        raise FileExistsError(f'Target already exists: {args["newPath"]}')
    os.makedirs(os.path.dirname(new_real) or ROOT, exist_ok=True)
    shutil.copy2(old_real, new_real)
    return None, False


def cmd_copy_folder(args):
    follow_symlinks = args.get('followSymlinks', False)
    old_real = real_path(args['oldPath'], follow_symlinks)
    new_real = real_path(args['newPath'], follow_symlinks)
    merge = args.get('merge', False)
    if not merge and os.path.exists(new_real):
        raise FileExistsError(f'Target already exists: {args["newPath"]}')
    if merge and os.path.exists(new_real):
        shutil.copytree(old_real, new_real, dirs_exist_ok=True)
    else:
        shutil.copytree(old_real, new_real)
    return None, False


def cmd_delete_file(args):
    path = args['path']
    follow_symlinks = args.get('followSymlinks', False)
    real = real_path(path, follow_symlinks)
    if not os.path.isfile(real):
        raise FileNotFoundError(f'File not found: {path}')
    os.remove(real)
    return None, False


def cmd_delete_folder(args):
    path = args['path']
    follow_symlinks = args.get('followSymlinks', False)
    real = real_path(path, follow_symlinks)
    if not os.path.isdir(real):
        raise FileNotFoundError(f'Folder not found: {path}')
    shutil.rmtree(real)
    return None, False


def cmd_storage_usage(_args):
    total, used, _free = shutil.disk_usage(ROOT)
    return {'usage': used, 'quota': total}, False

# ── Dispatch table ─────────────────────────────────────────────────────────────

COMMANDS = {
    'list':          cmd_list,
    'writeFile':     cmd_write_file,
    'addFolder':     cmd_add_folder,
    'moveFile':      cmd_move_file,
    'moveFolder':    cmd_move_folder,
    'copyFile':      cmd_copy_file,
    'copyFolder':    cmd_copy_folder,
    'deleteFile':    cmd_delete_file,
    'deleteFolder':  cmd_delete_folder,
    'storageUsage':  cmd_storage_usage,
}

ERROR_CODES = {
    FileExistsError:    'E:EXIST',
    FileNotFoundError:  'E:NOTFOUND',
    PermissionError:    'E:PERM',
    IsADirectoryError:  'E:ISDIR',
    NotADirectoryError: 'E:NOTDIR',
}

# ── Main loop ──────────────────────────────────────────────────────────────────

while True:
    msg = get_message()
    request_id = msg.get('requestId', '')
    cmd = msg.get('cmd', '')
    try:
        if cmd == 'readFile':
            # readFile handles its own sending (may produce multiple messages)
            cmd_read_file(request_id, msg)
        else:
            handler = COMMANDS.get(cmd)
            if handler is None:
                raise ValueError(f'Unknown command: {cmd}')
            result, _ = handler(msg)
            send_message({'requestId': request_id, 'ok': True, 'partial': False, 'result': result})
    except Exception as exc:
        error_code = ERROR_CODES.get(type(exc))
        send_message({
            'requestId': request_id,
            'ok': False,
            'error': str(exc),
            'errorCode': error_code,
        })
