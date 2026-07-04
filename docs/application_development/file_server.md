# File Server API

[← Back](index.md)

This API provides file management capabilities, allowing clients to upload,
retrieve, and manage files through various HTTP methods.
`http_files_api` must be set to `True` in
`pyrobusta.env` to enable this API.

---

## Table of Contents

* [File Server API](#file-server-api)
  + [Summary](#summary)
  + [File Retrieval](#file-retrieval-listing)
  + [File Upload / Overwrite](#file-upload-overwrite)
  + [Bulk File Upload](#bulk-file-upload)
  + [File Delete](#file-delete)

---

## Summary

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/files/{path}` | Lists or retrieves metadata about files. |
| `PUT` | `/files/{file path}` | Uploads or overwrites a file at the specified path. |
| `POST` | `/files` | Uploads multiple files in multipart/form-data. |
| `DELETE` | `/files/{file path}` | Deletes a file at the specified path. |

## File Retrieval / Listing

**Endpoint:** `GET /files/{path}`

This method allows general file system interaction, enabling operations
such as listing directory contents, retrieving metadata, and downloading
files.

* **Method:** `GET`
* **Path:** `/files/{path}`
* **Success Response:** `200 OK`

### Example Request

```
$ curl 192.168.1.100/files/www
[
    {"path": "/www/examples.html", "created": "90", "size": "4507"},
    {"path": "/www/index.html", "created": "91", "size": "1198"}
]
```

## File Upload / Overwrite

**Endpoint:** `PUT /files/{file path}`

This method uploads a file or overwrites an existing file at a specific
path. The upload path is restricted to
`/www/user_data`.

* **Method:** `PUT`
* **Path:** `/files/{file path}`
* **Body:** Raw file content (binary or text).
* **Success Response:** `201 Created`
* **Notes:**
  `transfer-encoding: chunked` is supported.

### Example Request

```
$ curl -X PUT --data 'This is a test.' \
http://192.168.1.100/files/www/user_data/test.txt
OK

$ curl 192.168.1.100/files/www/user_data/test.txt
This is a test.
```

## Bulk File Upload

**Endpoint:** `POST /files`

This method handles general file uploads, designed for uploading multiple
files with per-file chunking supported. Only
`multipart/form-data` is accepted.

Uploads are restricted to `/www/user_data`. The
`Content-Disposition` header only needs to specify the file
name; the upload directory is prepended automatically.

`http_multipart` must be set to `True` in the
configuration to use this method.

* **Method:** `POST`
* **Path:** `/files`
* **Body:**
  File content encapsulated in multipart/form-data.
* **Success Response:** `201 Created`

### Example Request

```
$ echo "File 1 content" > /tmp/upload-1.txt
$ echo "File 2 content" > /tmp/upload-2.txt

$ curl -X POST \
    --form file1='@/tmp/upload-1.txt' \
    --form file2='@/tmp/upload-2.txt' \
    http://192.168.1.100/files

$ curl 192.168.1.100/files/www/user_data
[
    {"path": "/www/user_data/upload-1.txt", "created": "418", "size": "15"},
    {"path": "/www/user_data/upload-2.txt", "created": "418", "size": "15"}
]
```

## File Delete

**Endpoint:** `DELETE /files/{file path}`

This method deletes a file at a specific path. The path is restricted to
`/www/user_data`.

* **Method:** `DELETE`
* **Path:** `/files/{file path}`
* **Success Response:** `204 No Content`

### Example Request

```
$ curl -X DELETE \
192.168.1.100/files/www/user_data/test.txt
```

---

PyRobusta v0.8.0 Web Server
