import os
import errno
import subprocess

try:
    import _version
    VERSION = _version.VERSION
except ImportError:
    VERSION = None

def version():
    return VERSION

def version_str():
    if version() is None:
        return "unknown"
    return version()

def generate(base_path, version=None):
    if version is None:
        version = _call("hg", "identify", "-i", base_path)
    if version is None:
        version = _parse_hg_archival(base_path)

    _generate_version_module(VERSION=version)

    global VERSION
    VERSION = version

def _call(*args):
    try:
        popen = subprocess.Popen(args, stdout=subprocess.PIPE)
    except OSError, (code, _):
        if code == errno.ENOENT:
            return None
        raise

    stdout, stderr = popen.communicate()
    if popen.returncode:
        return None
    return stdout.strip()

def _parse_hg_archival(base_path):
    try:
        archival = open(os.path.join(base_path, ".hg_archival.txt"))
        try:
            lines = list(archival.readlines())
        finally:
            archival.close()
    except IOError:
        return None

    data = dict(line.split(":", 1) for line in lines)
    if "node" in data:
        return data["node"].strip()[:12]
    return None

def _generate_version_module(**keys):
    version_dir, _ = os.path.split(__file__)

    module_file = open(os.path.join(version_dir, "_version.py"), "w")
    try:
        print >> module_file, "# This is an autogenerated file. Do not touch."
        for key, value in keys.items():
            print >> module_file, ("%s = %r" % (key, value))
    finally:
        module_file.close()

if __name__ == "__main__":
    print version_str()
