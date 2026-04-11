from os import listdir, remove, rmdir


def delete_path(path):
    for name in listdir(path):
        if path == "/":
            full = "/" + name
        else:
            full = path + "/" + name

        try:
            remove(full)
        except OSError:
            delete_path(full)
            try:
                rmdir(full)
            except OSError:
                pass


delete_path("/lib/pyrobusta")
delete_path("/www")

for f in ("/app.py", "/boot.py", "/pyrobusta.env", "/cert.der", "/key.der"):
    try:
        remove(f)
    except OSError:
        pass