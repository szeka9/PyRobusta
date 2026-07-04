# Static Content

[← Back](index.md)

PyRobusta serves static content directly from the filesystem. This page
describes the directory structure, file resolution rules, and MIME type
handling used by the server.

---

## Table of Contents

* [Static Content](#static-content)
  + [Static File Serving](#static-file-serving)
  + [Directory Structure](#directory-structure)
  + [MIME Type Handling](#mime-type-handling)

---

## Static File Serving

Files stored under `/www` are served as static content.
Requests to the server root (`/`) return the default landing page (`index.html`).
For static content requests, the server automatically prepends `/www` to the requested path before
resolving the corresponding file on the filesystem.

When the file management API is enabled (`http_files_api=True`),
additional filesystem locations can be exposed through the `http_served_paths`
configuration option. See the [Server Configuration](./configuration.md)
and [File Server API](./file_server.md) guide for additional details.

## Directory Structure

```
root/
├── www                     document root for static content
│   ├── index.html
│   ├── introduction.html
│   ├── ...
│   └── user_data           root for user uploads
│       └── ...
├── lib                     root for installed MIP packages
│   ├── pyrobusta
│   │   ├── bindings
│   │   ├── connectivity
│   │   └── ...
│   └── <other packages>
├── cert.der                TLS certificate
└── key.der                 TLS key
```

## MIME Type Handling

PyRobusta automatically determines the `Content-Type` header for
static files based on their filename extension. The selected content type depends on the file extension.
Unknown extensions are mapped to `application/octet-stream`.
The following mapping between extensions and content types is maintained by the server:

| Extension | Content-Type header |
| --- | --- |
| .html | text/html |
| .css | text/css |
| .js | application/javascript |
| .json | application/json |
| .ico | image/x-icon |
| .jpeg | image/jpeg |
| .jpg | image/jpeg |
| .png | image/png |
| .txt | text/plain |
| .gif | image/gif |
| .raw, unknown extensions | application/octet-stream |

---

PyRobusta v0.8.0 Web Server
